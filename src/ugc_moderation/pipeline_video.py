"""Video moderation pipeline (v2 hybrid — image-frame fanout).

Strategy: extract 1 frame per second, upload each frame to S3, moderate frames
in batches with early-exit on first deny. Any high-risk hit (confidence > 90%
on a high-risk label, or policy deny) short-circuits the whole video as deny
+ records the timestamp of the offending frame.

Two frame-extractor backends, chosen by env `VIDEO_FRAME_EXTRACTOR`:

  - "local"  (default when ffmpeg is on PATH) — subprocess to native ffmpeg
             binary. Fast local dev.
  - "ci"     (default for AgentCore Runtime, which doesn't ship ffmpeg) —
             upload mp4 to AgentCore Code Interpreter microVM, run ffmpeg
             there via the `imageio-ffmpeg` pip package (static binary), pull
             frame bytes back. Adds ~5s vs local but keeps all heavy deps
             inside AgentCore — no custom Docker image needed.

For POC the pipeline runs synchronously in-process (FastAPI same request).
Production would trigger this from S3 EventBridge → Lambda/Runtime — see
docs/solution.md.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from pydantic import BaseModel, Field

from .graph.state import DecisionOutput, ModerationReport
from .pipeline_hybrid import run_moderation_hybrid
from .settings import get_settings
from .tools.code_interpreter_tool import (
    _extract_stdout,
    ci_call_with_retry,
    get_shared_code_interpreter,
)
from .tools.s3_tool import _S3_CFG
from .util.logging import get_logger
from .util.media import parse_s3_uri, resize_for_nova
from .util.tracing import log_event, set_case, span

log = get_logger(__name__)

# Hard caps to keep demo predictable.
MAX_VIDEO_SECONDS = 90        # reject longer videos up-front
FRAMES_PER_SECOND = 1         # one frame per second
BATCH_SIZE = 5                # frames per concurrent wave


# ---- lightweight in-memory progress store (polled by /api/video/progress) --
# Not persisted — fine for POC single-process server. Keyed by case_id.
_PROGRESS: dict[str, dict[str, Any]] = {}


def get_progress(case_id: str) -> dict[str, Any] | None:
    return _PROGRESS.get(case_id)


def _progress_init(case_id: str) -> None:
    _PROGRESS[case_id] = {
        "case_id": case_id,
        "stage": "starting",
        "stage_label": "启动中…",
        "frames_done": 0,
        "frames_total": 0,
        "started_at": asyncio.get_event_loop().time(),
        "elapsed_s": 0.0,
        "done": False,
        "error": None,
    }


def _progress_set(case_id: str, **kwargs: Any) -> None:
    p = _PROGRESS.get(case_id)
    if p is None:
        return
    p.update(kwargs)
    p["elapsed_s"] = round(asyncio.get_event_loop().time() - p["started_at"], 2)
HIGH_RISK_LABELS = {
    "Explicit Nudity",
    "Explicit Sexual Activity",
    "Non-Explicit Nudity of Intimate parts and Kissing",
    "Violence",
    "Graphic Violence",
    "Visually Disturbing",
    "Hate Symbols",
}


class FrameResult(BaseModel):
    second: int
    s3_uri: str
    decision: str
    confidence: float
    top_label: str | None = None
    reasoning_cn: str
    risk_tags: list[str] = Field(default_factory=list)
    flag: int = 1
    # Set when this frame triggered early-exit
    short_circuit: bool = False


class VideoModerationReport(BaseModel):
    case_id: str
    content_s3_uri: str
    jurisdiction: str
    verdict: str                              # allow | deny | human_review
    reasoning_cn: str
    duration_s: float
    frames_sampled: int
    frames_evaluated: int                     # may be < sampled if short-circuited
    offending_frame: FrameResult | None = None
    frame_results: list[FrameResult] = Field(default_factory=list)
    summary_cn: str = ""                       # Nova Pro multi-frame summary
    summary_topic: str = ""                    # one-line topic tag
    flag: int = 1                              # overall severity flag (from worst frame)
    tags: list[str] = Field(default_factory=list)
    elapsed_s: float = 0.0


# --------------------------------------------------------------- helpers

def _s3_client():
    return boto3.client("s3", region_name=get_settings().aws_region, config=_S3_CFG)


def _pick_extractor() -> str:
    """Resolve frame extractor backend: env VIDEO_FRAME_EXTRACTOR overrides.

    Otherwise: use "local" if ffmpeg is on PATH, else "ci" (AgentCore Code
    Interpreter path). This matches the two deployment targets — dev box with
    ffmpeg installed, vs AgentCore Runtime which doesn't ship ffmpeg.
    """
    env = (os.getenv("VIDEO_FRAME_EXTRACTOR") or "").lower().strip()
    if env in ("local", "ci"):
        return env
    return "local" if shutil.which("ffmpeg") else "ci"


# ----- local ffmpeg path ---------------------------------------------------

def _probe_duration_local(video_path: Path) -> float:
    """Get video duration in seconds via ffprobe."""
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=nokey=1:noprint_wrappers=1", str(video_path),
        ],
        capture_output=True, text=True, timeout=30,
    )
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {out.stderr[:200]}")
    try:
        return float(out.stdout.strip())
    except ValueError:
        raise RuntimeError(f"ffprobe returned non-numeric: {out.stdout!r}")


def _extract_frames_local(video_path: Path, out_dir: Path, fps: int) -> list[Path]:
    """Extract 1-per-second frames as JPEGs, named frame_0001.jpg etc."""
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", f"fps={fps}",
        "-q:v", "3",
        str(out_dir / "frame_%04d.jpg"),
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {out.stderr[-400:]}")
    return sorted(out_dir.glob("frame_*.jpg"))


# ----- AgentCore Code Interpreter path -------------------------------------

_CI_FFMPEG_READY = False             # module-level latch; install once per process
_CI_FFMPEG_LOCK = None                # set in run_video_moderation to match asyncio loop


def _ensure_ci_ffmpeg_ready(ci) -> None:
    """Install imageio-ffmpeg in the shared CI session on first use."""
    global _CI_FFMPEG_READY
    if _CI_FFMPEG_READY:
        return
    with span("video.ci.install_ffmpeg"):
        ci_call_with_retry("install_packages", ["imageio-ffmpeg"])
    # Smoke-check the binary works
    smoke = ci_call_with_retry("invoke", "executeCode", {"language": "python", "code": (
        "import imageio_ffmpeg, subprocess; "
        "r = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-version'], "
        "capture_output=True, text=True, timeout=10); "
        "print('OK' if r.returncode == 0 else 'FAIL')"
    )})
    out = _extract_stdout(smoke)
    if "OK" not in out:
        raise RuntimeError(f"CI ffmpeg smoke check failed: {out[:200]}")
    _CI_FFMPEG_READY = True
    log.info("ci ffmpeg ready (imageio-ffmpeg static binary)")


def _probe_and_extract_via_ci(
    ci, video_bytes: bytes, fps: int, max_duration: float,
) -> tuple[float, list[tuple[int, bytes]]]:
    """Upload video to CI, run ffmpeg, pull frame bytes. Returns (duration, [(second, jpeg_bytes)])."""
    _ensure_ci_ffmpeg_ready(ci)

    with span("video.ci.upload", bytes=len(video_bytes)):
        ci.upload_file("input.mp4", video_bytes)

    code = f"""
import json, os, subprocess, imageio_ffmpeg
ff = imageio_ffmpeg.get_ffmpeg_exe()
# Probe duration via ffprobe-via-ffmpeg (read metadata)
probe = subprocess.run([ff, '-i', 'input.mp4'],
                       capture_output=True, text=True, timeout=30)
# ffmpeg writes metadata to stderr
import re
m = re.search(r'Duration:\\s*(\\d+):(\\d+):(\\d+\\.?\\d*)', probe.stderr)
duration = (int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))) if m else 0.0

os.makedirs('frames', exist_ok=True)
# Clean stale frames from prior run
for f in os.listdir('frames'):
    os.remove('frames/' + f)

rc = 0
if duration > {max_duration}:
    rc = -1
else:
    r = subprocess.run([ff, '-y', '-i', 'input.mp4',
                        '-vf', 'fps={fps}', '-q:v', '3',
                        'frames/frame_%04d.jpg'],
                       capture_output=True, text=True, timeout=120)
    rc = r.returncode

frames = sorted(os.listdir('frames')) if rc == 0 else []
print('MANIFEST:' + json.dumps({{
    'duration_s': duration, 'rc': rc, 'frames': frames,
}}))
"""
    with span("video.ci.extract_frames", fps=fps):
        resp = ci.invoke("executeCode", {"language": "python", "code": code})
    out = _extract_stdout(resp)
    manifest_line = next((l for l in out.splitlines() if l.startswith("MANIFEST:")), None)
    if not manifest_line:
        raise RuntimeError(f"CI frame extraction produced no manifest: {out[:400]}")
    manifest = json.loads(manifest_line[len("MANIFEST:"):])
    duration = float(manifest.get("duration_s") or 0.0)
    if manifest.get("rc") == -1:
        raise ValueError(f"Video too long: {duration:.1f}s > {max_duration}s demo cap")
    if manifest.get("rc") != 0:
        raise RuntimeError(f"CI ffmpeg failed (rc={manifest.get('rc')})")

    frame_names = manifest.get("frames") or []
    if not frame_names:
        raise RuntimeError("CI produced zero frames")

    # Download frames in one call
    with span("video.ci.download_frames", count=len(frame_names)):
        downloaded = ci.download_files([f"frames/{n}" for n in frame_names])

    frames_out: list[tuple[int, bytes]] = []
    for idx, name in enumerate(frame_names):
        key = f"frames/{name}"
        data = downloaded.get(key) or downloaded.get(f"/{key}") or downloaded.get(f"./{key}")
        if isinstance(data, str):
            # Some implementations return str; decode assuming latin-1 round-trip
            data = data.encode("latin-1", errors="ignore")
        if not data:
            log.warning("missing frame download", extra={"ctx_key": key})
            continue
        frames_out.append((idx, data))
    return duration, frames_out


_FRAME_VIOLATION_SYSTEM = """你是内容审核专家。下面这张图来自一段视频的某一帧，审核系统已判定它违规。
请输出严格 JSON，字段：
- scene_cn: 1~2 句具体描述画面内容（人物、动作、服饰、场景、物品、文字）
- violation_cn: 1~2 句解释为什么这张图违规，点出具体风险类型（如色情/血腥/武器/毒品/未成年/宗教敏感/引导性广告 等）
- risk_tags: 数组，1~3 个细粒度标签（例："色情"/"血腥暴力"/"武器"/"未成年"/"吸烟"/"宗教敏感"）
只输出 JSON，不要解释或 Markdown。"""


async def _describe_offending_frame(
    frame_bytes: bytes, top_label: str | None,
) -> tuple[str, list[str]]:
    """Ask Nova to describe WHAT the offending frame shows and WHY it violates.

    Returns (combined_reasoning_cn, risk_tags). On failure returns empty pair —
    caller should keep the original Sonnet reasoning as fallback.
    """
    settings = get_settings()
    client = boto3.client(
        "bedrock-runtime", region_name=settings.aws_region,
        config=Config(connect_timeout=10, read_timeout=60,
                      max_pool_connections=20,
                      retries={"max_attempts": 3, "mode": "adaptive"}),
    )
    hint = f"快筛给出的最高置信标签: {top_label}." if top_label else ""
    messages = [{
        "role": "user",
        "content": [
            {"image": {"format": "jpeg", "source": {"bytes": resize_for_nova(frame_bytes)}}},
            {"text": f"请审核这一帧。{hint}"},
        ],
    }]
    loop = asyncio.get_event_loop()
    def _call() -> dict[str, Any]:
        return client.converse(
            modelId=settings.nova_model_id,
            system=[{"text": _FRAME_VIOLATION_SYSTEM}],
            messages=messages,
            inferenceConfig={"maxTokens": 400, "temperature": 0.1},
        )
    try:
        with span("video.describe_offending"):
            resp = await loop.run_in_executor(None, _call)
        text = resp["output"]["message"]["content"][0]["text"].strip()
        if text.startswith("```"):
            text = text.strip("`").split("\n", 1)[-1].rsplit("```", 1)[0]
        parsed = json.loads(text)
        scene = str(parsed.get("scene_cn", "")).strip()
        violation = str(parsed.get("violation_cn", "")).strip()
        tags = [str(t) for t in (parsed.get("risk_tags") or [])][:4]
        combined = f"画面内容：{scene} 违规原因：{violation}" if (scene or violation) else ""
        return combined, tags
    except Exception as exc:       # noqa: BLE001
        log.warning("describe offending frame failed", extra={"ctx_err": str(exc)[:200]})
        return "", []


_SUMMARY_SYSTEM_CLEAN = """你是视频理解助手。下面是一段视频按时间均匀抽取的若干关键帧。
请结合这些帧推断视频主题，输出严格 JSON：
- topic: 不超过 15 字的主题短语（例：\"健身举重训练\" / \"户外徒步\"）
- summary_cn: 2~4 句中文概述，说明视频大致讲了什么、画面主要内容和氛围
只输出 JSON，不要解释或 Markdown。"""


_SUMMARY_SYSTEM_VIOLATION = """你是视频理解 + 审核助手。下面是一段视频的若干关键帧，其中标有 "[违规帧 t=Xs]" 的那一帧被审核系统判定为违规。
请输出严格 JSON：
- topic: 不超过 15 字的视频主题短语
- summary_cn: 3~5 句中文，结构为：(1) 视频整体在讲什么 (2) 违规帧画面具体在发生什么（人物动作/场景/物品/文字）(3) 为什么这违反内容规范，并明确点出风险类型
只输出 JSON，不要解释或 Markdown。"""


async def _summarize_video(
    frame_blobs: list[tuple[int, bytes]],
    offending: FrameResult | None,
) -> tuple[str, str]:
    """Call Nova Pro once on ≤4 representative frames to get a topic + summary.

    If an offending frame exists, the prompt changes to explicitly demand an
    explanation of WHAT the violating frame contains and WHY it violates.
    """
    if not frame_blobs:
        return "", ""
    # Pick representative frames: first, middle, last; plus offending if any.
    n = len(frame_blobs)
    picks = {0, n // 2, n - 1}
    offending_idx = -1
    if offending:
        # frame_blobs is [(idx, bytes)]; offending.second == idx in our pipeline
        for i, (sec, _b) in enumerate(frame_blobs):
            if sec == offending.second:
                picks.add(i)
                offending_idx = i
                break
    picks = sorted(picks)[:4]
    selected = [(i, frame_blobs[i]) for i in picks]

    content: list[dict[str, Any]] = []
    for i, (sec, raw) in selected:
        content.append({
            "image": {"format": "jpeg", "source": {"bytes": resize_for_nova(raw)}},
        })
        label = f"[违规帧 t={sec}s]" if i == offending_idx else f"[t={sec}s]"
        content.append({"text": label})
    content.append({
        "text": "请根据以上若干帧总结视频主题"
                + ("，并明确解释标注为违规帧的画面内容和违规理由。" if offending_idx >= 0 else "。")
    })

    system_prompt = _SUMMARY_SYSTEM_VIOLATION if offending_idx >= 0 else _SUMMARY_SYSTEM_CLEAN

    settings = get_settings()
    client = boto3.client(
        "bedrock-runtime", region_name=settings.aws_region,
        config=Config(connect_timeout=10, read_timeout=60,
                      max_pool_connections=20,
                      retries={"max_attempts": 3, "mode": "adaptive"}),
    )
    loop = asyncio.get_event_loop()
    def _call() -> dict[str, Any]:
        return client.converse(
            modelId=settings.nova_model_id,
            system=[{"text": system_prompt}],
            messages=[{"role": "user", "content": content}],
            inferenceConfig={"maxTokens": 500, "temperature": 0.2},
        )
    try:
        with span("video.summary", frames=len(selected),
                  mode="violation" if offending_idx >= 0 else "clean"):
            resp = await loop.run_in_executor(None, _call)
        text = resp["output"]["message"]["content"][0]["text"].strip()
        if text.startswith("```"):
            text = text.strip("`").split("\n", 1)[-1].rsplit("```", 1)[0]
        parsed = json.loads(text)
        return str(parsed.get("topic", "")).strip(), str(parsed.get("summary_cn", "")).strip()
    except Exception as exc:       # noqa: BLE001
        log.warning("video summary failed", extra={"ctx_err": str(exc)[:200]})
        return "", ""


def _upload_frame(s3, bucket: str, key: str, data: bytes) -> str:
    s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType="image/jpeg")
    return f"s3://{bucket}/{key}"


def _is_short_circuit_hit(report: ModerationReport) -> tuple[bool, str | None]:
    """Decide whether a single frame's report should halt the whole video.

    Rules (any one fires → short-circuit):
      1. Frame decision is deny
      2. Any Rekognition label in HIGH_RISK_LABELS with confidence > 90%
    """
    if report.decision.decision == "deny":
        return True, "frame_decision_deny"
    fs = report.fast_screen
    if fs:
        for lab in fs.labels or []:
            name = lab.get("Name")
            conf = float(lab.get("Confidence") or 0)
            if name in HIGH_RISK_LABELS and conf >= 90:
                return True, f"high_confidence:{name}@{conf:.1f}%"
    return False, None


# ----------------------------------------------------------------- entry

async def run_video_moderation(
    content_s3_uri: str,
    jurisdiction: str = "CN",
    tenant_id: str | None = None,
    session_id: str | None = None,
    case_id: str | None = None,
) -> VideoModerationReport:
    settings = get_settings()
    actor = tenant_id or settings.demo_tenant_id
    sid = session_id or str(uuid.uuid4())
    case_id = case_id or f"vcase-{sid[:8]}"
    set_case(case_id)
    started = asyncio.get_event_loop().time()
    _progress_init(case_id)
    _progress_set(case_id, stage="downloading", stage_label="① 下载视频…")

    log_event(case_id, "video.start", content_s3_uri=content_s3_uri,
              jurisdiction=jurisdiction)

    # ---------- 1. download video bytes from S3 (one-time, small object)
    bucket, key = parse_s3_uri(content_s3_uri)
    s3 = _s3_client()
    with span("video.s3_download", s3_uri=content_s3_uri):
        obj = s3.get_object(Bucket=bucket, Key=key)
        video_bytes = obj["Body"].read()

    # ---------- 2+3. probe duration + extract frames — via one of two backends
    extractor = _pick_extractor()
    log_event(case_id, "video.extractor_chosen", extractor=extractor)
    _progress_set(case_id, stage="extracting",
                  stage_label=f"② 抽帧中（{extractor}）…")

    frame_blobs: list[tuple[int, bytes]]             # [(second_index, jpeg_bytes)]
    if extractor == "ci":
        # Run upload+extract+download as one atomic group. If the microVM
        # session has expired mid-way, ci_call_with_retry would rebuild the
        # session but leave the /input.mp4 upload orphaned — so we do the
        # retry at the group level instead, from a clean slate each time.
        from .tools.code_interpreter_tool import (
            _is_session_dead as _ci_dead,
            _reset_shared_code_interpreter as _ci_reset,
        )
        loop = asyncio.get_event_loop()

        def _do_extract() -> tuple[float, list[tuple[int, bytes]]]:
            ci = get_shared_code_interpreter()
            if ci is None:
                raise RuntimeError(
                    "VIDEO_FRAME_EXTRACTOR=ci but AgentCore Code Interpreter not available"
                )
            return _probe_and_extract_via_ci(
                ci, video_bytes, FRAMES_PER_SECOND, float(MAX_VIDEO_SECONDS),
            )

        try:
            duration, frame_blobs = await loop.run_in_executor(None, _do_extract)
        except Exception as exc:                    # noqa: BLE001
            if not _ci_dead(exc):
                raise
            log.warning("CI session dead during extract; rebuilding and retrying",
                        extra={"ctx_err": str(exc)[:200]})
            _ci_reset()
            global _CI_FFMPEG_READY
            _CI_FFMPEG_READY = False
            duration, frame_blobs = await loop.run_in_executor(None, _do_extract)
    else:
        # local ffmpeg path
        tmp_root = Path(tempfile.mkdtemp(prefix="ugc_video_"))
        try:
            video_path = tmp_root / Path(key).name
            frames_dir = tmp_root / "frames"
            frames_dir.mkdir(parents=True, exist_ok=True)
            video_path.write_bytes(video_bytes)

            with span("video.ffprobe"):
                duration = _probe_duration_local(video_path)
            if duration > MAX_VIDEO_SECONDS:
                raise ValueError(
                    f"Video too long: {duration:.1f}s > {MAX_VIDEO_SECONDS}s demo cap"
                )
            with span("video.extract_frames_local", duration_s=duration, fps=FRAMES_PER_SECOND):
                frame_paths = _extract_frames_local(video_path, frames_dir, FRAMES_PER_SECOND)
            if not frame_paths:
                raise RuntimeError("ffmpeg produced zero frames")
            frame_blobs = [(i, p.read_bytes()) for i, p in enumerate(frame_paths)]
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)

    # ---------- 4. upload frames to S3
    frame_uris: list[tuple[int, str]] = []         # [(second_index, s3_uri), ...]
    _progress_set(case_id, stage="uploading_frames",
                  stage_label=f"③ 上传 {len(frame_blobs)} 帧到 S3…",
                  frames_total=len(frame_blobs))
    with span("video.upload_frames", count=len(frame_blobs)):
        for second, data in frame_blobs:
            frame_key = f"videoframes/{case_id}/sec_{second:03d}.jpg"
            uri = _upload_frame(s3, bucket, frame_key, data)
            frame_uris.append((second, uri))

    log_event(case_id, "video.frames_ready", count=len(frame_uris),
              duration_s=duration)

    # ---------- 5. moderate frames in batches, short-circuit on first hit
    frame_results: list[FrameResult] = []
    offending: FrameResult | None = None
    evaluated = 0

    async def _one_frame(second: int, uri: str) -> tuple[int, ModerationReport]:
        rep = await run_moderation_hybrid(
            content_s3_uri=uri,
            jurisdiction=jurisdiction,
            tenant_id=actor,
            session_id=f"{sid}-f{second}",
        )
        return second, rep

    _progress_set(case_id, stage="moderating",
                  stage_label=f"④ 逐帧审核 0/{len(frame_uris)}…",
                  frames_total=len(frame_uris), frames_done=0)
    with span("video.frame_fanout", total=len(frame_uris), batch_size=BATCH_SIZE):
        for batch_start in range(0, len(frame_uris), BATCH_SIZE):
            batch = frame_uris[batch_start:batch_start + BATCH_SIZE]
            pairs = await asyncio.gather(*[_one_frame(s, u) for s, u in batch])
            for second, rep in sorted(pairs, key=lambda p: p[0]):
                evaluated += 1
                hit, reason = _is_short_circuit_hit(rep)
                top_label = None
                if rep.fast_screen and rep.fast_screen.labels:
                    top_label = rep.fast_screen.labels[0].get("Name")
                fr = FrameResult(
                    second=second,
                    s3_uri=rep.content_s3_uri,
                    decision=rep.decision.decision,
                    confidence=float(rep.decision.confidence or 0),
                    top_label=top_label,
                    reasoning_cn=rep.decision.reasoning_cn,
                    risk_tags=list(rep.decision.tags or []),
                    flag=int(rep.decision.flag or 1),
                    short_circuit=hit,
                )
                frame_results.append(fr)
                if hit and offending is None:
                    offending = fr
                    log_event(case_id, "video.short_circuit", second=second,
                              reason=reason)
            _progress_set(
                case_id, frames_done=evaluated,
                stage_label=f"④ 逐帧审核 {evaluated}/{len(frame_uris)}…",
            )
            if offending is not None:
                break                               # stop at end of current batch

    # ---------- 5.5 if an offending frame exists, ask Nova to describe what's
    # happening in it and why it violates. Overwrites the generic Sonnet
    # reasoning with a concrete visual description + risk tags.
    if offending is not None:
        _progress_set(case_id, stage="describing_violation",
                      stage_label="⑤a 分析违规帧…")
        offending_bytes = next(
            (raw for sec, raw in frame_blobs if sec == offending.second), None,
        )
        if offending_bytes:
            combined, tags = await _describe_offending_frame(
                offending_bytes, offending.top_label,
            )
            if combined:
                offending.reasoning_cn = combined
                if tags:
                    offending.risk_tags = tags
                # keep frame_results entry in sync (offending is one of them)
                for idx, fr in enumerate(frame_results):
                    if fr.second == offending.second:
                        frame_results[idx] = offending
                        break

    # ---------- 6. video-level summary (one Nova call on ≤4 representative frames)
    _progress_set(case_id, stage="summarizing", stage_label="⑤b 生成视频主题与摘要…")
    topic, summary_cn = await _summarize_video(frame_blobs, offending)

    # ---------- 7. aggregate verdict
    elapsed = asyncio.get_event_loop().time() - started
    if offending:
        verdict = "deny"
        reasoning = (
            f"第 {offending.second}s 帧命中高风险内容：{offending.top_label or '未知标签'} · "
            f"{offending.reasoning_cn}"
        )
    else:
        # No single frame fired deny — aggregate: if majority allow, allow; else human_review
        denies = sum(1 for f in frame_results if f.decision == "deny")
        reviews = sum(1 for f in frame_results if f.decision == "human_review")
        if denies > 0:
            verdict = "deny"
            reasoning = f"{denies}/{len(frame_results)} 帧被拒绝，整体判定 deny。"
        elif reviews > len(frame_results) / 2:
            verdict = "human_review"
            reasoning = f"{reviews}/{len(frame_results)} 帧需人审，整体转人审。"
        else:
            verdict = "allow"
            reasoning = f"{len(frame_results)}/{len(frame_results)} 帧通过审核，整体 allow。"

    log_event(case_id, "video.end", verdict=verdict, evaluated=evaluated,
              elapsed_s=elapsed)
    _progress_set(case_id, stage="done", stage_label="✅ 完成", done=True,
                  verdict=verdict)

    # Overall flag = worst (highest) among frames; tags merged from top few.
    overall_flag = max((f.flag for f in frame_results), default=1)
    overall_tags: list[str] = []
    seen: set[str] = set()
    for f in sorted(frame_results, key=lambda x: -x.flag):
        for t in f.risk_tags:
            if t and t not in seen:
                seen.add(t)
                overall_tags.append(t)
        if len(overall_tags) >= 5:
            break

    return VideoModerationReport(
        case_id=case_id,
        content_s3_uri=content_s3_uri,
        jurisdiction=jurisdiction,
        verdict=verdict,
        reasoning_cn=reasoning,
        duration_s=duration,
        frames_sampled=len(frame_uris),
        frames_evaluated=evaluated,
        offending_frame=offending,
        frame_results=frame_results,
        summary_cn=summary_cn,
        summary_topic=topic,
        flag=overall_flag,
        tags=overall_tags,
        elapsed_s=round(elapsed, 2),
    )


def report_to_dict(report: VideoModerationReport) -> dict[str, Any]:
    import json as _json
    return _json.loads(report.model_dump_json())

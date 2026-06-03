"""FastAPI backend for the UGC moderation demo UI.

Run:
    uv sync --extra api
    uv run uvicorn backend.api:app --reload --port 8000

Serves REST endpoints consumed by the React SPA in `ui/`.
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Make src/ importable
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from ugc_moderation.pipeline import report_to_dict, run_moderation as _run_agent  # noqa: E402
from ugc_moderation.pipeline_hybrid import (  # noqa: E402
    run_moderation_hybrid as _run_hybrid,
    run_moderation_hybrid_multi as _run_hybrid_multi,
    run_moderation_replay as _run_replay,
)
from ugc_moderation.pipeline_video import (  # noqa: E402
    MAX_VIDEO_SECONDS,
    get_progress as _video_get_progress,
    run_video_moderation,
    report_to_dict as _video_report_to_dict,
)
from ugc_moderation.settings import DEFAULT_AGENT_MODELS, get_settings  # noqa: E402
from ugc_moderation.tools.code_interpreter_tool import (  # noqa: E402
    get_shared_code_interpreter,
    stop_shared_code_interpreter,
)


async def run_moderation(**kwargs):
    """Dispatch to the pipeline selected by PIPELINE_MODE (agent | hybrid)."""
    mode = (get_settings().pipeline_mode or "agent").lower()
    if mode == "hybrid":
        return await _run_hybrid(**kwargs)
    return await _run_agent(**kwargs)
from ugc_moderation.tools.memory_tool import (  # noqa: E402
    _mem_client,
    record_misjudgment,
)
from ugc_moderation.tools.s3_tool import upload_bytes_to_demo_bucket  # noqa: E402
from ugc_moderation.util.tracing import trace_file  # noqa: E402


Jurisdiction = Literal["CN", "EU", "US"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm up the shared Code Interpreter session at startup so the first
    # /api/moderate doesn't pay the 3-4s microVM cold start. If the video
    # pipeline is routed to CI extractor, also pre-install imageio-ffmpeg so
    # the first /api/video/moderate doesn't pay the pip-install cost.
    loop = asyncio.get_running_loop()
    try:
        ci = await loop.run_in_executor(None, get_shared_code_interpreter)
        if ci is not None:
            from ugc_moderation.pipeline_video import (
                _ensure_ci_ffmpeg_ready,
                _pick_extractor,
            )
            if _pick_extractor() == "ci":
                await loop.run_in_executor(None, _ensure_ci_ffmpeg_ready, ci)
    except Exception:                           # noqa: BLE001 - best effort
        pass
    yield
    stop_shared_code_interpreter()


app = FastAPI(title="UGC Moderation API", version="0.2.0", lifespan=lifespan)

# Open CORS for local dev; tighten in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------- models

class ModerateRequest(BaseModel):
    content_s3_uri: str
    jurisdiction: Jurisdiction = "CN"
    ocr_text: str = ""
    session_id: str | None = None


class MultiJurisdictionRequest(BaseModel):
    content_s3_uri: str
    jurisdictions: list[Jurisdiction] = ["CN", "EU", "US"]
    ocr_text: str = ""


class BatchRequest(BaseModel):
    content_s3_uris: list[str]
    jurisdiction: Jurisdiction = "CN"


class MisjudgmentRequest(BaseModel):
    case_id: str
    jurisdiction: Jurisdiction
    original_decision: str
    corrected_decision: str
    summary: str


class ReplayRequest(BaseModel):
    """Re-run the decision stage using a previously returned report as cache."""
    previous_report: dict[str, Any]
    session_id: str | None = None


# ------------------------------------------------------------------- routes

@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True}


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    s = get_settings()
    return {
        "aws_region": s.aws_region,
        "nova_model_id": s.nova_model_id,
        "agent_models": {k: s.model_for(k) for k in DEFAULT_AGENT_MODELS},
        "memory_id": s.memory_id,
        "guardrail_id": s.guardrail_id,
        "code_interpreter_id": s.code_interpreter_id,
        "demo_bucket": s.demo_bucket,
        "default_confidence_threshold": s.default_confidence_threshold,
        "client_mode": s.client_mode,
        "agent_runtime_arn": s.agent_runtime_arn,
        "pipeline_mode": s.pipeline_mode,
    }


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> dict[str, Any]:
    ct = file.content_type or ""
    if not (ct.startswith("image/") or ct.startswith("video/")):
        raise HTTPException(400, "Only image and video uploads are supported.")
    raw = await file.read()
    key = f"uploads/{uuid.uuid4()}-{file.filename}"
    uri = upload_bytes_to_demo_bucket(raw, key=key, content_type=ct)
    return {"s3_uri": uri, "size_bytes": len(raw), "content_type": ct}


class VideoModerateRequest(BaseModel):
    content_s3_uri: str
    jurisdiction: Jurisdiction = "CN"
    session_id: str | None = None
    case_id: str | None = None


@app.post("/api/video/moderate")
async def video_moderate(req: VideoModerateRequest) -> dict[str, Any]:
    """Moderate a short video by extracting 1 frame / second, fanning out
    frames through the image hybrid pipeline, short-circuiting on first
    high-risk hit. Demo cap: 90s videos."""
    try:
        rep = await run_video_moderation(
            content_s3_uri=req.content_s3_uri,
            jurisdiction=req.jurisdiction,
            session_id=req.session_id,
            case_id=req.case_id,
        )
    except ValueError as exc:          # too long / unsupported
        raise HTTPException(400, str(exc))
    except Exception as exc:           # noqa: BLE001
        raise HTTPException(500, f"Video moderation failed: {str(exc)[:300]}")
    return _video_report_to_dict(rep)


@app.get("/api/video/limits")
def video_limits() -> dict[str, Any]:
    return {"max_video_seconds": MAX_VIDEO_SECONDS, "frames_per_second": 1, "batch_size": 5}


@app.get("/api/video/progress/{case_id}")
def video_progress(case_id: str) -> dict[str, Any]:
    p = _video_get_progress(case_id)
    if p is None:
        raise HTTPException(404, "Unknown case_id (pipeline not started or already evicted)")
    return p


@app.post("/api/moderate")
async def moderate(req: ModerateRequest) -> dict[str, Any]:
    report = await run_moderation(
        content_s3_uri=req.content_s3_uri,
        jurisdiction=req.jurisdiction,
        session_id=req.session_id,
        ocr_text=req.ocr_text,
    )
    return report_to_dict(report)


@app.post("/api/moderate/multi")
async def moderate_multi(req: MultiJurisdictionRequest) -> dict[str, Any]:
    """Run N jurisdictions on one image.

    In hybrid mode we share upstream work (Memory/Rekognition/Nova/TextGuard)
    across all jurisdictions and only fan out the decision stage — ~2.5× faster
    than the agent-mode gather-3-full-runs path. In agent mode we keep the
    naive gather since full-Graph shares nothing.
    """
    s = get_settings()
    if s.pipeline_mode == "hybrid":
        try:
            results = await _run_hybrid_multi(
                content_s3_uri=req.content_s3_uri,
                jurisdictions=list(req.jurisdictions),
                ocr_text=req.ocr_text,
            )
            return {"results": {j: report_to_dict(r) for j, r in results.items()}}
        except Exception as exc:   # noqa: BLE001
            return {"results": {j: {"error": str(exc)[:200]} for j in req.jurisdictions}}

    # Agent mode — each Graph run is fully independent, just gather.
    async def _one(j: str):
        try:
            rep = await run_moderation(
                content_s3_uri=req.content_s3_uri,
                jurisdiction=j,
                ocr_text=req.ocr_text,
            )
            return j, report_to_dict(rep)
        except Exception as exc:       # noqa: BLE001
            return j, {"error": str(exc)[:200]}

    results = await asyncio.gather(*[_one(j) for j in req.jurisdictions])
    return {"results": {j: r for j, r in results}}


_BATCH_CONCURRENCY = 4        # cap so we don't self-throttle on Bedrock quotas
_batch_sem = asyncio.Semaphore(_BATCH_CONCURRENCY)


@app.post("/api/batch")
async def batch(req: BatchRequest) -> dict[str, Any]:
    """Run N distinct images through moderation, bounded concurrent.

    Unlike /api/moderate/multi (same image × N jurisdictions), batch items
    are fully distinct — no signal sharing. Bound concurrency with a semaphore
    so 10 images don't all hammer Bedrock at once and hit adaptive throttling.
    """
    async def _one(uri: str):
        try:
            async with _batch_sem:
                rep = await run_moderation(content_s3_uri=uri, jurisdiction=req.jurisdiction)
            return report_to_dict(rep)
        except Exception as exc:       # noqa: BLE001
            return {"content_s3_uri": uri, "error": str(exc)[:200]}

    started = asyncio.get_event_loop().time()
    reports = await asyncio.gather(*[_one(u) for u in req.content_s3_uris])
    return {
        "elapsed_s": round(asyncio.get_event_loop().time() - started, 2),
        "reports": reports,
    }


@app.post("/api/moderate/replay")
async def moderate_replay(req: ReplayRequest) -> dict[str, Any]:
    """Re-decide a previous report — skips Rekognition/Nova, runs only Memory
    recall + decision. Used by MemoryPage to close the 'misjudgment → re-run'
    loop in ~8s instead of ~25s."""
    from ugc_moderation.graph.state import ModerationReport as _MR  # local import
    try:
        prev = _MR.model_validate(req.previous_report)
    except Exception as exc:       # noqa: BLE001
        raise HTTPException(400, f"Invalid previous_report: {exc}")

    rep = await _run_replay(previous_report=prev, session_id=req.session_id)
    return report_to_dict(rep)


@app.post("/api/misjudgment")
def misjudgment(req: MisjudgmentRequest) -> dict[str, Any]:
    return record_misjudgment(
        case_id=req.case_id,
        original_decision=req.original_decision,
        corrected_decision=req.corrected_decision,
        signals_summary=req.summary,
        jurisdiction=req.jurisdiction,
    )


@app.get("/api/memory/recent")
def memory_recent(limit: int = 20) -> dict[str, Any]:
    s = get_settings()
    if not s.memory_id:
        return {"records": []}
    try:
        resp = _mem_client().list_memory_records(
            memoryId=s.memory_id,
            namespace=f"/misjudgments/{s.demo_tenant_id}",
            maxResults=limit,
        )
    except Exception as exc:           # noqa: BLE001
        raise HTTPException(500, f"Memory list failed: {exc}")
    records = []
    for r in resp.get("memoryRecordSummaries", []):
        content = (r.get("content") or {}).get("text", "")
        records.append({
            "memory_id": r.get("memoryRecordId"),
            "content": content,
            "created_at": (r.get("createdAt") or "").isoformat() if hasattr(r.get("createdAt"), "isoformat") else str(r.get("createdAt", "")),
        })
    return {"records": records}


@app.get("/api/trace/latest")
def trace_latest(case_id: str | None = None) -> dict[str, Any]:
    path = trace_file()
    if not path.exists():
        return {"case_id": None, "spans": [], "events": []}
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not rows:
        return {"case_id": None, "spans": [], "events": []}

    target = case_id or rows[-1].get("case_id")
    rows = [r for r in rows if r.get("case_id") == target]

    # Pair starts with ends to build spans
    starts: dict[str, dict] = {}
    spans: list[dict] = []
    events: list[dict] = []
    origin = None
    for r in rows:
        phase = r.get("phase")
        if phase == "start":
            starts[r["span_id"]] = r
            if origin is None:
                origin = r.get("wall")
        elif phase == "end":
            st = starts.pop(r["span_id"], None)
            if st:
                spans.append({
                    "span": st["span"],
                    "start_ms": round((st["wall"] - origin) * 1000, 1) if origin else 0,
                    "dur_ms": r.get("dur_ms", 0),
                    "extra": st.get("extra") or {},
                })
        elif "event" in r:
            events.append({"event": r["event"], "extra": r.get("extra") or {}})

    spans.sort(key=lambda s: s["start_ms"])
    return {"case_id": target, "spans": spans, "events": events}

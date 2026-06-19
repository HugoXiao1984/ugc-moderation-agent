"""Run jurisdiction policy scripts inside an AgentCore Code Interpreter microVM.

The source of truth for each policy lives in `policies_scripts/{cn,eu,us}.py`.
Each invocation:
  1. Reads common.py + the jurisdiction file from disk.
  2. Builds a small wrapper that calls `evaluate(signals)` and prints JSON.
  3. Sends the wrapper to `CodeInterpreter.invoke("executeCode", ...)`.
  4. Parses the emitted stdout.

This keeps rules hot-swappable (change the .py files, no Agent redeploy).
If the AgentCore SDK isn't available or the CI session fails, we fall back
to running the scripts locally so development is unblocked.

Session lifecycle:
  - Old path (still available as fallback): `code_session(region)` context
    manager — creates + destroys a microVM session for every call (~3-4s
    cold start each time).
  - New path: `get_shared_code_interpreter()` returns a module-level
    singleton started once and reused across requests. 3× faster for
    multi-jurisdiction fan-out (and any subsequent audit in the same
    process).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from strands import tool

from ..policies import JURISDICTIONS, scripts_dir
from ..settings import get_settings
from ..util.logging import get_logger
from ..util.tracing import span

log = get_logger(__name__)

# --------------------------------------------------------- shared session

_SHARED_CI = None
_SHARED_LOCK = threading.Lock()


def get_shared_code_interpreter():
    """Return a long-lived CodeInterpreter session, creating it on first use.

    AgentCore CodeInterpreter.invoke() is thread-safe for independent
    executeCode calls (each call is a fresh kernel execution in the same
    microVM). FastAPI handlers can call this directly.
    """
    global _SHARED_CI
    if _SHARED_CI is not None:
        return _SHARED_CI
    with _SHARED_LOCK:
        if _SHARED_CI is not None:
            return _SHARED_CI
        try:
            from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreter
        except ImportError:
            log.info("bedrock_agentcore SDK not installed; using local fallback")
            return None
        settings = get_settings()
        try:
            with span("ci.shared_session.start"):
                ci = CodeInterpreter(settings.aws_region)
                if settings.code_interpreter_id:
                    ci.identifier = settings.code_interpreter_id
                # Default session_timeout is 900s (15 min); AgentCore reaps the
                # session after that idle window, so a demo run >15 min after
                # startup hits a dead session on every frame. Widen to 1h to
                # cut that failure window (the rebuild-on-stale logic in
                # _run_in_code_interpreter / ci_call_with_retry still covers
                # the case where it expires anyway). Configurable via env.
                ci.start(session_timeout_seconds=settings.ci_session_timeout_seconds)
            _SHARED_CI = ci
            log.info("shared code interpreter session started",
                     extra={"ctx_sid": getattr(ci, "session_id", None)})
            return _SHARED_CI
        except Exception as exc:                 # noqa: BLE001
            log.warning("shared CI session failed to start; will fall back",
                        extra={"ctx_err": str(exc)[:200]})
            _SHARED_CI = None
            return None


def stop_shared_code_interpreter() -> None:
    """Call from FastAPI lifespan shutdown to release the microVM."""
    global _SHARED_CI
    with _SHARED_LOCK:
        if _SHARED_CI is None:
            return
        try:
            _SHARED_CI.stop()
            log.info("shared code interpreter session stopped")
        except Exception as exc:                 # noqa: BLE001
            log.warning("CI stop failed", extra={"ctx_err": str(exc)[:200]})
        _SHARED_CI = None


def _reset_shared_code_interpreter(stale=None) -> None:
    """Force-drop the cached session (e.g. after 'session not active' error).

    Next get_shared_code_interpreter() call will create a fresh microVM. Caller
    should also reset any per-process latches that depend on the old session
    (e.g. the imageio-ffmpeg install latch in pipeline_video).

    If `stale` is given, only drop the cached session when it is still that
    exact object. Under concurrent video batches several frames may hit the
    same dead session at once; this guard stops a late frame from killing a
    session another frame already rebuilt.
    """
    global _SHARED_CI
    with _SHARED_LOCK:
        old = _SHARED_CI
        if stale is not None and old is not stale:
            return                               # already replaced by someone else
        _SHARED_CI = None
    if old is not None:
        try:
            old.stop()
        except Exception:                        # noqa: BLE001
            pass


def _is_session_dead(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        "session" in msg and ("not active" in msg or "not found" in msg or "expired" in msg)
    ) or "validationexception" in msg and "not active" in msg


def ci_call_with_retry(method_name: str, *args: Any, **kwargs: Any) -> Any:
    """Call `method_name` on the shared CI session, auto-rebuilding once if
    the session has gone stale. Returns the raw method result. Raises if CI
    is unavailable (no SDK) or the second attempt also fails.

    Used by the video pipeline (upload_file / download_files / invoke), which
    can't tolerate a silent fallback — frames live inside the microVM.
    """
    ci = get_shared_code_interpreter()
    if ci is None:
        raise RuntimeError("CodeInterpreter unavailable (SDK missing or start failed)")
    try:
        return getattr(ci, method_name)(*args, **kwargs)
    except Exception as exc:                     # noqa: BLE001
        if not _is_session_dead(exc):
            raise
        log.warning("CI session dead; rebuilding and retrying",
                    extra={"ctx_method": method_name, "ctx_err": str(exc)[:160]})
        _reset_shared_code_interpreter(stale=ci)
        # Reset the ffmpeg-install latch so the rebuilt session re-installs it.
        try:
            from .. import pipeline_video
            pipeline_video._CI_FFMPEG_READY = False
        except Exception:                        # noqa: BLE001
            pass
        ci2 = get_shared_code_interpreter()
        if ci2 is None:
            raise RuntimeError("Failed to rebuild CI session after stale error")
        return getattr(ci2, method_name)(*args, **kwargs)

_WRAPPER_TEMPLATE = """\
{common_src}

{policy_src}

import json, sys
_signals = json.loads({signals_json!r})
_result = evaluate(_signals)
print(json.dumps(_result.to_dict(), ensure_ascii=False))
"""


def _load_script(name: str) -> str:
    path: Path = scripts_dir() / f"{name}.py"
    return path.read_text(encoding="utf-8")


def _build_wrapper(jurisdiction: str, signals: dict) -> str:
    common_src = _load_script("common")
    policy_src = _load_script(jurisdiction.lower())
    # Strip `from common import ...` lines — we've inlined common_src above.
    cleaned = "\n".join(
        line for line in policy_src.splitlines()
        if not line.startswith("from common import")
    )
    return _WRAPPER_TEMPLATE.format(
        common_src=common_src,
        policy_src=cleaned,
        signals_json=json.dumps(signals, ensure_ascii=False),
    )


def _run_in_code_interpreter(wrapper: str) -> dict[str, Any] | None:
    # Preferred path: reuse the module-level shared CodeInterpreter session
    # to avoid the 3-4s microVM cold start on every call.
    ci = get_shared_code_interpreter()
    if ci is not None:
        try:
            with span("tool:code_interpreter.shared"):
                resp = ci.invoke("executeCode", {"language": "python", "code": wrapper})
                stdout = _extract_stdout(resp)
                if not stdout:
                    return None
                return json.loads(stdout.splitlines()[-1])
        except Exception as exc:                 # noqa: BLE001
            # If the shared session went stale (e.g. AgentCore reaped it after
            # idle), rebuild it ONCE and retry on the fresh session. Without
            # this, the dead session stays cached and every subsequent call
            # (e.g. every video frame) re-fails and pays a one-shot cold start
            # — turning a fast video into a 504-risking crawl.
            if _is_session_dead(exc):
                log.warning("shared CI session stale; rebuilding once",
                            extra={"ctx_err": str(exc)[:160]})
                _reset_shared_code_interpreter(stale=ci)
                ci2 = get_shared_code_interpreter()
                if ci2 is not None:
                    try:
                        with span("tool:code_interpreter.shared.retry"):
                            resp = ci2.invoke("executeCode", {"language": "python", "code": wrapper})
                            stdout = _extract_stdout(resp)
                            if not stdout:
                                return None
                            return json.loads(stdout.splitlines()[-1])
                    except Exception as exc2:    # noqa: BLE001
                        log.warning("rebuilt CI call failed; falling back to one-shot",
                                    extra={"ctx_err": str(exc2)[:200]})
            else:
                log.warning("shared CI call failed; retrying with one-shot session",
                            extra={"ctx_err": str(exc)[:200]})
            # Fall through to ephemeral session

    # Fallback: ephemeral code_session (cold-start each call)
    try:
        from bedrock_agentcore.tools.code_interpreter_client import code_session
    except ImportError:
        return None
    region = get_settings().aws_region
    try:
        with span("tool:code_interpreter"):
            with code_session(region) as sess:
                resp = sess.invoke("executeCode", {"language": "python", "code": wrapper})
                stdout = _extract_stdout(resp)
                if not stdout:
                    return None
                return json.loads(stdout.splitlines()[-1])
    except Exception as exc:                     # noqa: BLE001 - demo fallback
        log.warning("code interpreter failed", extra={"ctx_err": str(exc)[:200]})
        return None


def _extract_stdout(resp: Any) -> str:
    """AgentCore Code Interpreter streams events; we prefer structuredContent.stdout.

    The content[0].text field is a duplicate of stdout — only use it as a fallback.
    """
    stream = resp.get("stream") if isinstance(resp, dict) else getattr(resp, "stream", None)
    if stream is None:
        return ""
    stdout_parts: list[str] = []
    text_parts: list[str] = []
    for event in stream:
        data = event.get("result") or event
        structured = data.get("structuredContent") or {}
        if structured.get("stdout"):
            stdout_parts.append(structured["stdout"])
            continue
        for item in data.get("content", []) or []:
            if item.get("type") == "text" and item.get("text"):
                text_parts.append(item["text"])
    return ("\n".join(stdout_parts) or "\n".join(text_parts)).strip()


@tool
def run_jurisdiction_policy(jurisdiction: str, signals: dict[str, Any]) -> dict[str, Any]:
    """Execute cn/eu/us.py under AgentCore Code Interpreter.

    Args:
        jurisdiction: "CN" | "EU" | "US".
        signals: Dict containing labels, nova_reasoning, guardrail, ocr_text,
                 orchestrator_hints.

    Returns:
        PolicyResult dict (decision / violated_rules / reasoning_cn / confidence /
        escalation_needed / thresholds_used) plus an `execution_mode` indicator.
    """
    jurisdiction = jurisdiction.upper()
    if jurisdiction not in JURISDICTIONS:
        raise ValueError(f"Unknown jurisdiction: {jurisdiction}")

    wrapper = _build_wrapper(jurisdiction, signals)
    remote = _run_in_code_interpreter(wrapper)
    if remote is not None:
        remote["execution_mode"] = "code_interpreter"
        return remote

    # Local fallback (dev mode or AgentCore unavailable)
    local = JURISDICTIONS[jurisdiction].evaluate(signals).to_dict()
    local["execution_mode"] = "local_fallback"
    return local

"""Call the deployed AgentCore Runtime via InvokeAgentRuntime.

This is the *remote* execution path for moderation. The Fargate backend tries
this first when CLIENT_MODE=remote and AGENT_RUNTIME_ARN is set; on ANY failure
the caller falls back to running the pipeline in-process (the always-available
ECS path), so enabling remote can never regress the working demo.

The Runtime entrypoint is src/ugc_moderation/app.py — it accepts the same
payload shape and returns report_to_dict(report) as application/json.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import boto3
from botocore.config import Config

from .settings import get_settings
from .util.logging import get_logger

log = get_logger(__name__)

# Bound the remote call so a hung Runtime can't pin a request longer than the
# in-process path would have taken. Generous enough for a full moderation run.
_RT_CFG = Config(
    connect_timeout=5,
    read_timeout=150,
    retries={"max_attempts": 2, "mode": "standard"},
)


def remote_enabled() -> bool:
    """True when the backend is configured to prefer the remote Runtime."""
    s = get_settings()
    return (s.client_mode or "").lower() == "remote" and bool(s.agent_runtime_arn)


def _client():
    return boto3.client(
        "bedrock-agentcore", region_name=get_settings().aws_region, config=_RT_CFG
    )


def _coerce_bytes(chunk: Any) -> bytes:
    if isinstance(chunk, (bytes, bytearray)):
        return bytes(chunk)
    return str(chunk).encode("utf-8")


def _parse_response(resp: dict[str, Any]) -> dict[str, Any]:
    """Reassemble the streamed/JSON body into a dict.

    IMPORTANT: concatenate the raw *bytes* first, then decode once. The body is
    chunked on arbitrary byte boundaries, so decoding each chunk independently
    splits multi-byte UTF-8 characters (the Chinese reasoning text) and raises
    UnicodeDecodeError.
    """
    content_type = resp.get("contentType", "") or ""
    body = resp.get("response")

    if "text/event-stream" in content_type:
        # Streaming entrypoints emit `data: <chunk>` lines.
        raw = b"".join(_coerce_bytes(line) for line in body.iter_lines(chunk_size=1024) if line)
        text = raw.decode("utf-8")
        parts = [ln[len("data: "):] for ln in text.splitlines() if ln.startswith("data: ")]
        return json.loads("".join(parts) if parts else text)

    # JSON (or unspecified): gather all bytes, decode once.
    if hasattr(body, "read"):                     # StreamingBody
        raw = body.read()
    elif isinstance(body, (list, tuple)) or hasattr(body, "__iter__"):
        raw = b"".join(_coerce_bytes(c) for c in body)
    else:
        raw = _coerce_bytes(body)
    return json.loads(raw.decode("utf-8"))


def _invoke_runtime(payload_obj: dict[str, Any], session_id: str | None = None) -> dict[str, Any]:
    """Low-level: POST a JSON payload to the Runtime, return the parsed dict.

    Raises on transport/parse error so callers can fall back.
    """
    s = get_settings()
    arn = s.agent_runtime_arn
    if not arn:
        raise RuntimeError("AGENT_RUNTIME_ARN not configured")

    payload = json.dumps(payload_obj).encode("utf-8")

    # runtimeSessionId must be unique per logical conversation and is required
    # to be >= 33 chars by the API. A hex uuid4 (32) + prefix clears the bar.
    base = (session_id or str(uuid.uuid4())).replace("-", "")
    rt_session = f"sess{base}".ljust(33, "0")

    resp = _client().invoke_agent_runtime(
        agentRuntimeArn=arn,
        runtimeSessionId=rt_session,
        payload=payload,
    )
    return _parse_response(resp)


def synthesize_decision_remote(
    jurisdiction: str,
    signals: dict[str, Any],
    policy: dict[str, Any],
    memory_rationale: list[str],
    session_id: str | None = None,
) -> dict[str, Any]:
    """Run the single Sonnet synthesis agent in the AgentCore Runtime.

    This is the one stage we genuinely offload to the Runtime microVM. The
    payload is small (no image, no S3 — just the pre-computed PolicyResult and
    upstream signals), so the Runtime agent never needs cross-region S3 access.

    Returns the raw decision JSON blob (the caller finalizes/validates it).
    Raises on any failure so the caller can fall back to local Sonnet.

    Retries once on an empty blob: a freshly-deployed/scaled microVM can return
    {"blob": {}} on its very first request while warming, and a single retry
    against the now-warm instance succeeds — cheaper than dropping to the local
    fallback for what is a transient cold-start artifact.
    """
    payload = {
        "task": "decision_synthesis",
        "jurisdiction": jurisdiction,
        "signals": signals,
        "policy": policy,
        "memory_rationale": memory_rationale,
    }
    last_result: Any = None
    for attempt in range(2):
        result = _invoke_runtime(payload, session_id=session_id)
        last_result = result
        if isinstance(result, dict):
            # entrypoint wraps the blob as {"blob": {...}}; accept a bare blob too.
            blob = result.get("blob") if "blob" in result else result
            if isinstance(blob, dict) and "decision" in blob:
                return blob
        if attempt == 0:
            log.warning("runtime synthesis returned empty blob; retrying once (cold start)")
    raise RuntimeError(f"Runtime synthesis returned no decision: {str(last_result)[:200]}")


def invoke_moderation_remote(
    content_s3_uri: str,
    jurisdiction: str = "CN",
    tenant_id: str | None = None,
    session_id: str | None = None,
    ocr_text: str = "",
) -> dict[str, Any]:
    """Invoke the deployed AgentCore Runtime and return a report dict.

    Raises on any transport/parse error so the caller can fall back. Returns a
    dict matching report_to_dict(); raises if the Runtime returned an error
    envelope instead of a report.
    """
    s = get_settings()
    result = _invoke_runtime(
        {
            "content_s3_uri": content_s3_uri,
            "jurisdiction": jurisdiction,
            "tenant_id": tenant_id or s.demo_tenant_id,
            "session_id": session_id or str(uuid.uuid4()),
            "ocr_text": ocr_text,
        },
        session_id=session_id,
    )

    # The entrypoint returns report_to_dict on success. Treat an explicit error
    # field, or a missing decision, as a failure worth falling back on.
    if not isinstance(result, dict) or "decision" not in result:
        raise RuntimeError(f"Runtime returned no decision: {str(result)[:200]}")
    return result

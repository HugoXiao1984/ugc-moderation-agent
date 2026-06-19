"""AgentCore Runtime entrypoint (Firecracker microVM per session)."""
from __future__ import annotations

import uuid
from typing import Any

import sys
from pathlib import Path

# When AgentCore Runtime runs this file as __main__, the package isn't on
# sys.path yet — add the parent `src/` so absolute imports work.
_PKG_PARENT = Path(__file__).resolve().parent.parent
if str(_PKG_PARENT) not in sys.path:
    sys.path.insert(0, str(_PKG_PARENT))

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from ugc_moderation.pipeline import report_to_dict, run_moderation as _run_agent
from ugc_moderation.pipeline_hybrid import (
    _synthesize_blob_local,
    run_moderation_hybrid as _run_hybrid,
)
from ugc_moderation.settings import get_settings


async def run_moderation(**kwargs):
    mode = (get_settings().pipeline_mode or "agent").lower()
    if mode == "hybrid":
        return await _run_hybrid(**kwargs)
    return await _run_agent(**kwargs)

app = BedrockAgentCoreApp()


def _handle_decision_synthesis(payload: dict[str, Any]) -> dict[str, Any]:
    """Single-agent task: run ONLY the Sonnet decision synthesis in the Runtime.

    This is the demo of "one agent genuinely running in AgentCore Runtime". The
    caller (ECS) has already done Rekognition/Nova/Guardrail/Memory/policy and
    hands us a small JSON; we do exactly one Sonnet round-trip and return the raw
    decision blob. No S3, no tools — so the Runtime role needs only Bedrock
    InvokeModel, sidestepping the cross-region S3 IAM that broke the old
    whole-pipeline Runtime.
    """
    blob = _synthesize_blob_local(
        jurisdiction=payload.get("jurisdiction", "CN"),
        signals=payload.get("signals", {}),
        policy=payload.get("policy", {}),
        memory_rationale=payload.get("memory_rationale", []),
    )
    return {"blob": blob}


@app.entrypoint
async def invoke(payload: dict[str, Any]) -> dict[str, Any]:
    """Runtime entrypoint — dispatches on the optional `task` field.

    task == "decision_synthesis": run only the Sonnet decision agent. Payload:
        {"task": "decision_synthesis", "jurisdiction", "signals", "policy",
         "memory_rationale"} → {"blob": {...raw decision JSON...}}

    otherwise (default): run the full moderation pipeline (back-compat). Payload:
        {"content_s3_uri", "jurisdiction"?, "tenant_id"?, "session_id"?, "ocr_text"?}
    """
    if payload.get("task") == "decision_synthesis":
        return _handle_decision_synthesis(payload)

    settings = get_settings()
    content_s3_uri = payload["content_s3_uri"]
    jurisdiction = payload.get("jurisdiction", "CN")
    tenant_id = payload.get("tenant_id", settings.demo_tenant_id)
    session_id = payload.get("session_id", str(uuid.uuid4()))
    ocr_text = payload.get("ocr_text", "")

    report = await run_moderation(
        content_s3_uri=content_s3_uri,
        jurisdiction=jurisdiction,
        tenant_id=tenant_id,
        session_id=session_id,
        ocr_text=ocr_text,
    )
    return report_to_dict(report)


if __name__ == "__main__":
    app.run()

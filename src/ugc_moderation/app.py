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
from ugc_moderation.pipeline_hybrid import run_moderation_hybrid as _run_hybrid
from ugc_moderation.settings import get_settings


async def run_moderation(**kwargs):
    mode = (get_settings().pipeline_mode or "agent").lower()
    if mode == "hybrid":
        return await _run_hybrid(**kwargs)
    return await _run_agent(**kwargs)

app = BedrockAgentCoreApp()


@app.entrypoint
async def invoke(payload: dict[str, Any]) -> dict[str, Any]:
    """Moderation entrypoint.

    Expected payload:
        {
          "content_s3_uri": "s3://bucket/key.jpg",
          "jurisdiction": "CN" | "EU" | "US",
          "tenant_id": "<optional>",
          "session_id": "<optional>",
          "ocr_text": "<optional: pre-extracted caption/OCR>"
        }
    """
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

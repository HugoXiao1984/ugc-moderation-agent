"""Bedrock Guardrails text-moderation tool."""
from __future__ import annotations

from typing import Any

import boto3
from botocore.config import Config
from strands import tool

from ..settings import get_settings
from ..util.logging import get_logger
from ..util.tracing import span

log = get_logger(__name__)

_BEDROCK_CFG = Config(connect_timeout=5, read_timeout=20,
                      max_pool_connections=20,
                      retries={"max_attempts": 3, "mode": "adaptive"})


def _bedrock():
    return boto3.client("bedrock-runtime", region_name=get_settings().aws_region, config=_BEDROCK_CFG)


@tool
def apply_guardrail(text: str, guardrail_id: str | None = None, version: str | None = None) -> dict[str, Any]:
    """Run text through a Bedrock Guardrail (INPUT scope).

    Args:
        text: The text to evaluate.
        guardrail_id: Override the default from settings.
        version: Override the default version (e.g. "DRAFT" or a numeric ver).

    Returns:
        {"action": "NONE"|"GUARDRAIL_INTERVENED",
         "blocked_topics": [...], "blocked_pii": [...], "raw": <full response>}
    """
    s = get_settings()
    gid = guardrail_id or s.guardrail_id
    gver = version or s.guardrail_version
    if not gid:
        return {"action": "NONE", "blocked_topics": [], "blocked_pii": [], "raw": {"skipped": "no guardrail configured"}}

    with span("tool:apply_guardrail", guardrail_id=gid, text_len=len(text)):
        resp = _bedrock().apply_guardrail(
            guardrailIdentifier=gid,
            guardrailVersion=gver,
            source="INPUT",
            content=[{"text": {"text": text}}],
        )
    action = resp.get("action", "NONE")
    assessments = resp.get("assessments") or []
    topics: list[str] = []
    pii: list[str] = []
    for a in assessments:
        for t in (a.get("topicPolicy") or {}).get("topics", []):
            topics.append(t.get("name", ""))
        for p in (a.get("sensitiveInformationPolicy") or {}).get("piiEntities", []):
            pii.append(p.get("type", ""))
    log.info("guardrail result", extra={"ctx_action": action, "ctx_topics": topics})
    return {"action": action, "blocked_topics": topics, "blocked_pii": pii, "raw": resp}

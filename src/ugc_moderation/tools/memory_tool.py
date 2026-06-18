"""AgentCore Memory tools: recall similar cases, record misjudgments."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3
from strands import tool

from ..memory.namespaces import misjudgment_namespace
from ..settings import get_settings
from ..util.logging import get_logger
from ..util.tracing import span

log = get_logger(__name__)


def _mem_client():
    return boto3.client("bedrock-agentcore", region_name=get_settings().aws_region)


@tool
def recall_similar_cases(
    case_summary: str,
    jurisdiction: str,
    actor_id: str | None = None,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """Query AgentCore Memory for similar past misjudgments.

    Args:
        case_summary: Natural-language description of the new content
            (e.g., "一张健身房举重肌肉特写图片").
        jurisdiction: CN | EU | US.
        actor_id: Tenant id.
        top_k: Max hits.

    Returns:
        List of {memory_id, content, relevance_score, corrected_decision, signals}.
    """
    settings = get_settings()
    if not settings.memory_id:
        return []

    actor = actor_id or settings.demo_tenant_id
    namespace = misjudgment_namespace(actor, jurisdiction)

    try:
        with span("tool:memory.retrieve", namespace=namespace, top_k=top_k):
            resp = _mem_client().retrieve_memory_records(
                memoryId=settings.memory_id,
                namespace=namespace,
                searchCriteria={"searchQuery": case_summary, "topK": top_k},
            )
    except Exception as exc:                     # noqa: BLE001
        log.warning("memory retrieve failed", extra={"ctx_err": str(exc)[:200]})
        return []

    results = []
    for rec in resp.get("memoryRecordSummaries", []):
        content = (rec.get("content") or {}).get("text", "")
        meta = _extract_metadata(content)
        results.append({
            "memory_id": rec.get("memoryRecordId"),
            "content": content,
            "relevance_score": rec.get("score", 0.0),
            "corrected_decision": meta.get("corrected_decision"),
            "signals_summary": meta.get("summary"),
        })
    return results


@tool
def record_misjudgment(
    case_id: str,
    original_decision: str,
    corrected_decision: str,
    signals_summary: str,
    jurisdiction: str,
    actor_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Write a misjudgment event into AgentCore Memory.

    The event text is natural language (good for semantic retrieval) plus a
    JSON metadata sidecar recoverable via `_extract_metadata`.
    """
    settings = get_settings()
    if not settings.memory_id:
        return {"ok": False, "reason": "memory not configured"}

    actor = actor_id or settings.demo_tenant_id
    sid = session_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    narrative = (
        f"在 {jurisdiction} 法域下，案例 {case_id} 的原决策为 {original_decision}，"
        f"运营更正为 {corrected_decision}。内容摘要：{signals_summary}。"
        f"建议：下次命中相似内容时，若原判 deny 则适度放宽阈值；若原判 allow 则收紧阈值。"
        f"时间：{now}。"
    )
    metadata = {
        "case_id": case_id,
        "original_decision": original_decision,
        "corrected_decision": corrected_decision,
        "summary": signals_summary,
    }
    payload = f"{narrative}\n<!--metadata:{json.dumps(metadata, ensure_ascii=False)}-->"

    try:
        with span("tool:memory.create_event", actor=actor, session=sid):
            _mem_client().create_event(
                memoryId=settings.memory_id,
                actorId=actor,
                sessionId=sid,
                payload=[{"conversational": {"role": "USER", "content": {"text": payload}}}],
                eventTimestamp=now,
            )
    except Exception as exc:                     # noqa: BLE001
        log.warning("memory create_event failed", extra={"ctx_err": str(exc)[:200]})
        return {"ok": False, "reason": str(exc)[:200]}

    return {"ok": True, "case_id": case_id, "session_id": sid}


_DECISION = r"(allow|deny|human_review)"


def _parse_corrected_decision(text: str) -> str | None:
    """Best-effort recovery of the corrected decision from free text.

    The semantic memory strategy rewrites the stored event into a new
    natural-language sentence and drops our `<!--metadata-->` sidecar, so we
    can't rely on the JSON comment after extraction. Both the original CN
    narrative ("运营更正为 allow") and the English rewrite produced by the
    strategy ("operations corrected it to allow", "corrected by operations to
    deny") are handled here.
    """
    t = text.lower()
    # English: "corrected it to allow" / "corrected by operations to deny" / "corrected to allow"
    m = re.search(rf"correct(?:ed|ion|s)?\b[^.;]*?\bto\s+{_DECISION}", t)
    if m:
        return m.group(1)
    # Chinese: "更正为 allow" / "运营更正为 deny"
    m = re.search(rf"更正为\s*{_DECISION}", t)
    if m:
        return m.group(1)
    return None


def _extract_metadata(content: str) -> dict[str, Any]:
    # Fast path: raw (non-extracted) reads still carry the JSON sidecar.
    marker = "<!--metadata:"
    if marker in content:
        try:
            raw = content.split(marker, 1)[1].rsplit("-->", 1)[0]
            return json.loads(raw)
        except Exception:                        # noqa: BLE001
            pass
    # Fallback: recover the corrected decision from the (possibly rewritten)
    # narrative so semantic-extracted records still drive threshold tuning.
    corrected = _parse_corrected_decision(content)
    return {"corrected_decision": corrected} if corrected else {}

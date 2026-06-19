"""High-level pipeline wrapper that runs the Graph and assembles a ModerationReport.

Used by:
  - `app.py` (AgentCore Runtime entrypoint)
  - `streamlit_app/client.py` (local mode)
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from strands.multiagent.base import Status

from .graph import build_moderation_graph, build_moderation_task
from .graph.conditions import _parse_last_json_blob
from .graph.state import (
    DecisionOutput,
    DeepReviewOutput,
    FastScreenOutput,
    ModerationReport,
    OrchestratorOutput,
    TextGuardOutput,
)
from .memory.session_manager import build_session_manager
from .settings import get_settings
from .util.logging import get_logger
from .util.tracing import log_event, set_case, span

log = get_logger(__name__)


def _extract(state_results, node_id: str, model_cls):
    node = state_results.get(node_id)
    if node is None or node.status != Status.COMPLETED:
        return None
    raw = getattr(node, "output", None) or getattr(node, "result", None) or ""
    blob = _parse_last_json_blob(str(raw))
    if not blob:
        return None
    try:
        return model_cls.model_validate(blob)
    except Exception as exc:               # noqa: BLE001
        log.warning("validation failed", extra={"ctx_node": node_id, "ctx_err": str(exc)[:200]})
        return None


async def run_moderation(
    content_s3_uri: str,
    jurisdiction: str = "CN",
    tenant_id: str | None = None,
    session_id: str | None = None,
    ocr_text: str = "",
) -> ModerationReport:
    settings = get_settings()
    actor = tenant_id or settings.demo_tenant_id
    sid = session_id or str(uuid.uuid4())
    case_id = f"case-{sid[:8]}"
    set_case(case_id)

    task = build_moderation_task(content_s3_uri, jurisdiction, ocr_text)

    log_event(case_id, "invocation.start",
              content_s3_uri=content_s3_uri, jurisdiction=jurisdiction)
    with span("pipeline", case_id, jurisdiction=jurisdiction, content_s3_uri=content_s3_uri):
        with span("build_session_manager", case_id):
            sm_ctx = build_session_manager(actor, sid, jurisdiction)
            _sm = sm_ctx.__enter__()
        try:
            with span("build_graph", case_id):
                graph = build_moderation_graph()
            with span("graph.invoke_async", case_id):
                result = await graph.invoke_async(
                    task,
                    invocation_state={
                        "content_s3_uri": content_s3_uri,
                        "jurisdiction": jurisdiction,
                        "tenant_id": actor,
                        "session_id": sid,
                    },
                )
            # Per-node durations from Strands Graph result (execution_time is ms)
            for node in (result.execution_order or []):
                node_id = getattr(node, "node_id", str(node))
                ms = getattr(node, "execution_time", None)
                if ms is None:
                    ms = getattr(node, "elapsed_time", None)
                log_event(case_id, "node.complete",
                          node_id=node_id,
                          execution_time_ms=(round(ms, 1) if isinstance(ms, (int, float)) else None))
        finally:
            sm_ctx.__exit__(None, None, None)

    orch = _extract(result.results, "orchestrator", OrchestratorOutput) or OrchestratorOutput(
        modality="image", jurisdiction=jurisdiction, effective_threshold=75.0
    )
    fs = _extract(result.results, "fast_screen", FastScreenOutput)
    dr = _extract(result.results, "deep_review", DeepReviewOutput)
    tg = _extract(result.results, "text_guard", TextGuardOutput)
    # Exactly one of decision_light / decision_heavy fires per run (mutually
    # exclusive conditions). Try both nodes and take whichever completed.
    decision = (
        _extract(result.results, "decision_heavy", DecisionOutput)
        or _extract(result.results, "decision_light", DecisionOutput)
        or _extract(result.results, "decision", DecisionOutput)       # back-compat
        or DecisionOutput(
            decision="human_review",
            reasoning_cn="决策节点未产出结构化输出，保守转人审。",
            confidence=0.3,
            jurisdiction=jurisdiction,
            execution_mode="local_fallback",
        )
    )

    log_event(case_id, "invocation.end",
              decision=decision.decision, trace=[n.node_id for n in (result.execution_order or [])])

    return ModerationReport(
        case_id=case_id,
        content_s3_uri=content_s3_uri,
        jurisdiction=jurisdiction,
        orchestrator=orch,
        fast_screen=fs,
        deep_review=dr,
        text_guard=tg,
        decision=decision,
        trace=[n.node_id for n in (result.execution_order or [])],
    )


def run_moderation_sync(**kwargs) -> ModerationReport:
    return asyncio.run(run_moderation(**kwargs))


def report_to_dict(report: ModerationReport | dict[str, Any]) -> dict[str, Any]:
    # Idempotent on dicts: the remote AgentCore Runtime path already returns a
    # report dict, so callers can pass either a ModerationReport or that dict.
    if isinstance(report, dict):
        return report
    return json.loads(report.model_dump_json())

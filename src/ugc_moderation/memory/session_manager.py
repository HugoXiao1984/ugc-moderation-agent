"""Thin wrapper around AgentCoreMemorySessionManager.

Falls back to a no-op context manager when the AgentCore SDK or MEMORY_ID
isn't available — lets dev run the Graph locally without a real memory.
"""
from __future__ import annotations

import contextlib
from typing import Any

from ..settings import get_settings
from ..util.logging import get_logger
from .namespaces import (
    misjudgment_namespace,
    operator_prefs_namespace,
    session_summary_namespace,
)

log = get_logger(__name__)


@contextlib.contextmanager
def build_session_manager(actor_id: str, session_id: str, jurisdiction: str = "CN"):
    """Yield an AgentCoreMemorySessionManager (or None in fallback mode)."""
    settings = get_settings()
    if not settings.memory_id:
        log.info("memory disabled (no MEMORY_ID)")
        yield None
        return

    try:
        from bedrock_agentcore.memory.integrations.strands.session_manager import (
            AgentCoreMemorySessionManager,
        )
        from bedrock_agentcore.memory.integrations.strands.config import (
            AgentCoreMemoryConfig,
            RetrievalConfig,
        )
    except ImportError as exc:
        log.warning("agentcore memory sdk not installed", extra={"ctx_err": str(exc)})
        yield None
        return

    # Semantic-strategy scores for similar cases sit ~0.35-0.45 (the strategy
    # rewrites stored text, lowering cosine similarity), so a 0.7-0.75 gate
    # filters out every real hit. Align with MEMORY_RELEVANCE_GATE.
    gate = settings.memory_relevance_gate
    retrieval: dict[str, RetrievalConfig] = {
        misjudgment_namespace(actor_id, jurisdiction): RetrievalConfig(top_k=3, relevance_score=gate),
        operator_prefs_namespace(actor_id): RetrievalConfig(top_k=2, relevance_score=gate),
    }
    config = AgentCoreMemoryConfig(
        memory_id=settings.memory_id,
        session_id=session_id,
        actor_id=actor_id,
        retrieval_config=retrieval,
    )

    with AgentCoreMemorySessionManager(agentcore_memory_config=config, region_name=settings.aws_region) as sm:
        yield sm


def summary_namespace_for(actor_id: str, session_id: str) -> str:
    return session_summary_namespace(actor_id, session_id)


def get_memory_config() -> dict[str, Any]:
    """Expose the live Memory resource identifiers for diagnostics."""
    s = get_settings()
    return {
        "memory_id": s.memory_id,
        "region": s.aws_region,
        "actor_default": s.demo_tenant_id,
    }

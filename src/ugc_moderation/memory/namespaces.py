"""Namespace templates for AgentCore Memory resources."""
from __future__ import annotations


def misjudgment_namespace(actor_id: str, jurisdiction: str | None = None) -> str:
    """Single per-actor namespace; jurisdiction is encoded into the narrative text."""
    return f"/misjudgments/{actor_id}"


def operator_prefs_namespace(actor_id: str) -> str:
    return f"/operator_prefs/{actor_id}"


def session_summary_namespace(actor_id: str, session_id: str) -> str:
    return f"/summaries/{actor_id}/{session_id}"


# Template patterns registered when creating the Memory resource.
STRATEGY_NAMESPACE_TEMPLATES = {
    "semantic": "/misjudgments/{actorId}",
    "preference": "/operator_prefs/{actorId}",
    "summary": "/summaries/{actorId}/{sessionId}",
}

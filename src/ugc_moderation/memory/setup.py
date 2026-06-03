"""Create the Memory resource with the three strategies we use."""
from __future__ import annotations

from typing import Any

from ..settings import get_settings
from ..util.logging import get_logger

log = get_logger(__name__)


def create_memory_resource(name: str = "UGCModerationMemory") -> dict[str, Any]:
    """Creates the Memory resource (idempotent by name) and returns metadata.

    Uses the high-level bedrock_agentcore MemoryClient which also handles
    `create_memory_and_wait`.
    """
    from bedrock_agentcore.memory.client import MemoryClient

    settings = get_settings()
    client = MemoryClient(region_name=settings.aws_region)

    # AgentCore Memory namespaces only accept {actorId}/{sessionId}/{memoryStrategyId} placeholders.
    # Jurisdiction is encoded into the narrative text and metadata; semantic retrieval
    # disambiguates CN / EU / US cases naturally.
    strategies = [
        {
            "semanticMemoryStrategy": {
                "name": "MisjudgmentCases",
                "namespaces": ["/misjudgments/{actorId}"],
            }
        },
        {
            "userPreferenceMemoryStrategy": {
                "name": "OperatorPreferences",
                "namespaces": ["/operator_prefs/{actorId}"],
            }
        },
        {
            "summaryMemoryStrategy": {
                "name": "SessionSummary",
                "namespaces": ["/summaries/{actorId}/{sessionId}"],
            }
        },
    ]

    result = client.create_memory_and_wait(name=name, strategies=strategies)
    memory_id = result.get("memoryId") or result.get("id")
    log.info("memory created", extra={"ctx_id": memory_id, "ctx_name": name})
    return {"memory_id": memory_id, "result": result}

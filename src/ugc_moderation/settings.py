"""Central settings loaded from env / .env file."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

# --- Model tier defaults (speed-first tier, quality tier) --------------------
# Haiku 4.5: ~2-3x faster, ~10x cheaper; good enough for tool_use + JSON output.
# Sonnet 4.6: best reasoning + Chinese fluency; reserved for final decision.
# Nova Pro: multimodal (image understanding); only used by deep_review TOOL.
MODEL_FAST = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
MODEL_QUALITY = "global.anthropic.claude-sonnet-4-6"
MODEL_NOVA = "us.amazon.nova-pro-v1:0"

# Per-agent defaults: orchestrator / fast_screen / text_guard / deep_review use
# the fast tier; decision_heavy uses quality tier. decision_light stays fast.
DEFAULT_AGENT_MODELS: dict[str, str] = {
    "orchestrator": MODEL_FAST,
    "fast_screen": MODEL_FAST,
    "text_guard": MODEL_FAST,
    "deep_review": MODEL_FAST,         # outer agent; the Nova tool does the vision work
    "decision_light": MODEL_FAST,       # low-risk path — fast ruling
    "decision_heavy": MODEL_QUALITY,    # high/medium-risk path — explainable CN reasoning
}


@dataclass(frozen=True)
class Settings:
    aws_region: str
    nova_model_id: str
    # Kept for backwards compatibility (was single global model).
    decision_model_id: str
    # Per-agent overrides — merged with DEFAULT_AGENT_MODELS on read.
    agent_models: dict[str, str] = field(default_factory=dict)
    memory_id: str | None = None
    guardrail_id: str | None = None
    guardrail_version: str = "DRAFT"
    code_interpreter_id: str | None = None
    demo_tenant_id: str = "demo-tenant"
    demo_bucket: str = "ugc-moderation-demo"
    default_confidence_threshold: float = 75.0
    # Min relevance score for a recalled misjudgment to drive threshold tuning.
    # Semantic-strategy scores for similar cases sit ~0.35-0.45, so the old
    # hard-coded 0.75 never matched.
    memory_relevance_gate: float = 0.40
    client_mode: str = "local"
    agent_runtime_arn: str | None = None
    # Pipeline engine: "agent" = original full-Graph (6 Agents) / "hybrid" = pipeline_hybrid
    # (2 Agents + deterministic steps). Default stays "agent" for backward compat.
    pipeline_mode: str = "agent"

    def model_for(self, agent_name: str) -> str:
        """Resolve the model id for a given agent, honoring env overrides."""
        return self.agent_models.get(agent_name, DEFAULT_AGENT_MODELS.get(agent_name, self.decision_model_id))


def _load_agent_models() -> dict[str, str]:
    """Load per-agent overrides from AGENT_MODEL_<NAME> env vars.

    Examples:
        AGENT_MODEL_DECISION_HEAVY=global.anthropic.claude-sonnet-4-6
        AGENT_MODEL_ORCHESTRATOR=global.anthropic.claude-haiku-4-5
    """
    overrides: dict[str, str] = {}
    for key, val in os.environ.items():
        if key.startswith("AGENT_MODEL_") and val:
            agent_key = key[len("AGENT_MODEL_"):].lower()
            overrides[agent_key] = val
    return overrides


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # Back-compat: if DECISION_MODEL_ID is set, it overrides decision_heavy default.
    legacy_decision = os.getenv("DECISION_MODEL_ID")
    overrides = _load_agent_models()
    if legacy_decision and "decision_heavy" not in overrides:
        overrides["decision_heavy"] = legacy_decision
    return Settings(
        aws_region=os.getenv("AWS_REGION", "us-east-1"),
        nova_model_id=os.getenv("NOVA_MODEL_ID", MODEL_NOVA),
        decision_model_id=legacy_decision or MODEL_QUALITY,
        agent_models=overrides,
        memory_id=os.getenv("MEMORY_ID") or None,
        guardrail_id=os.getenv("GUARDRAIL_ID") or None,
        guardrail_version=os.getenv("GUARDRAIL_VERSION", "DRAFT"),
        code_interpreter_id=os.getenv("CODE_INTERPRETER_ID") or None,
        demo_tenant_id=os.getenv("DEMO_TENANT_ID", "demo-tenant"),
        demo_bucket=os.getenv("DEMO_BUCKET", "ugc-moderation-demo"),
        default_confidence_threshold=float(os.getenv("DEFAULT_CONFIDENCE_THRESHOLD", "75")),
        memory_relevance_gate=float(os.getenv("MEMORY_RELEVANCE_GATE", "0.40")),
        client_mode=os.getenv("CLIENT_MODE", "local"),
        agent_runtime_arn=os.getenv("AGENT_RUNTIME_ARN") or None,
        pipeline_mode=(os.getenv("PIPELINE_MODE", "agent") or "agent").lower(),
    )

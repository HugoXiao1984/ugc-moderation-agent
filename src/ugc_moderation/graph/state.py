"""Structured output types exchanged between Graph nodes.

Each Agent is asked (via system prompt) to return JSON matching these Pydantic
models, which are then pushed onto the GraphState under the node id.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Jurisdiction = Literal["CN", "EU", "US"]
Modality = Literal["image", "video", "text", "mixed"]
Decision = Literal["allow", "deny", "human_review"]


class OrchestratorOutput(BaseModel):
    modality: Modality
    jurisdiction: Jurisdiction
    prior_risk: Literal["low", "medium", "high"] = "medium"
    effective_threshold: float = 75.0
    memory_hits: list[dict[str, Any]] = Field(default_factory=list)
    memory_rationale: list[str] = Field(default_factory=list)
    routing_hint: str = ""
    needs_text_guard: bool = False


class FastScreenOutput(BaseModel):
    max_confidence: float = 0.0
    labels: list[dict[str, Any]] = Field(default_factory=list)
    has_text: bool = False
    has_person: bool = False
    trigger_deep_review: bool = False


class DeepReviewOutput(BaseModel):
    verdict: Decision
    confidence: float
    risk_tags: list[str] = Field(default_factory=list)
    reasoning_cn: str
    ocr_text: str = ""


class TextGuardOutput(BaseModel):
    action: Literal["NONE", "GUARDRAIL_INTERVENED"]
    blocked_topics: list[str] = Field(default_factory=list)
    blocked_pii: list[str] = Field(default_factory=list)


class DecisionOutput(BaseModel):
    decision: Decision
    reasoning_cn: str
    violated_rules: list[str] = Field(default_factory=list)
    confidence: float
    escalation_needed: bool = False
    jurisdiction: Jurisdiction
    execution_mode: str = "code_interpreter"
    thresholds_used: dict[str, float] = Field(default_factory=dict)
    memory_rationale: list[str] = Field(default_factory=list)
    # Extended tag/flag scoring (coexists with decision=allow/deny/human_review).
    # flag convention: 999 (最严重) / 998 / 997 / 200 / 100 / 1 / 2 — see prompt.
    flag: int = 1
    tags: list[str] = Field(default_factory=list)


class ModerationReport(BaseModel):
    """Final payload returned from the AgentCore entrypoint."""
    case_id: str
    content_s3_uri: str
    jurisdiction: Jurisdiction
    orchestrator: OrchestratorOutput
    fast_screen: FastScreenOutput | None = None
    deep_review: DeepReviewOutput | None = None
    text_guard: TextGuardOutput | None = None
    decision: DecisionOutput
    trace: list[str] = Field(default_factory=list)

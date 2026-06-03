"""Shared types for jurisdiction policy scripts.

Executed either directly (unit tests, src/ugc_moderation/policies mirror) or
injected into an AgentCore Code Interpreter sandbox prefix.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PolicyResult:
    decision: str                     # "allow" | "deny" | "human_review"
    violated_rules: list[str] = field(default_factory=list)
    reasoning_cn: str = ""
    confidence: float = 0.0
    escalation_needed: bool = False
    thresholds_used: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_labels(labels: list[dict]) -> dict[str, float]:
    """Rekognition label list -> {name: confidence}."""
    out: dict[str, float] = {}
    for lab in labels or []:
        name = lab.get("Name") or lab.get("name")
        conf = lab.get("Confidence") or lab.get("confidence") or 0.0
        if name:
            out[name] = max(float(conf), out.get(name, 0.0))
    return out


def any_label_above(labels: dict[str, float], thresholds: dict[str, float]) -> list[tuple[str, float, float]]:
    """Return [(label, confidence, threshold)] for every violation."""
    hits = []
    for name, thresh in thresholds.items():
        conf = labels.get(name, 0.0)
        if conf > thresh:
            hits.append((name, conf, thresh))
    return hits

"""Conditional edge functions for the moderation Graph.

Strands Graph default edge semantics are OR — we use AND-style guards where a
downstream node (`decision`) must only fire once all *required* upstream
branches have completed. The `required` set is computed from the
orchestrator's output (text-only content skips fast_screen, etc.).
"""
from __future__ import annotations

import json
from typing import Any

try:                                        # Strands may not be importable in unit tests
    from strands.multiagent.base import Status
except Exception:                            # noqa: BLE001
    class Status:                            # type: ignore[no-redef]
        COMPLETED = "COMPLETED"

from .state import FastScreenOutput, OrchestratorOutput

HIGH_RISK_LABEL_NAMES = {
    "Explicit Nudity",
    "Non-Explicit Nudity of Intimate parts and Kissing",
    "Violence",
    "Graphic Violence",
    "Visually Disturbing",
    "Hate Symbols",
}


def _parse_last_json_blob(text: str) -> dict[str, Any]:
    """Strands Agents return free text; find the last JSON object in it."""
    start, depth, in_str, esc = -1, 0, False, False
    last_obj = None
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                chunk = text[start:i + 1]
                try:
                    last_obj = json.loads(chunk)
                except json.JSONDecodeError:
                    pass
                start = -1
    return last_obj or {}


def _node_output(state, node_id: str):
    node = state.results.get(node_id)
    if node is None or node.status != Status.COMPLETED:
        return None
    raw = getattr(node, "output", None) or getattr(node, "result", None) or ""
    text = str(raw)
    return _parse_last_json_blob(text)


def _completed(state, node_id: str) -> bool:
    node = state.results.get(node_id)
    return bool(node and node.status == Status.COMPLETED)


def route_to_fast_screen(state) -> bool:
    """Orchestrator → fast_screen: skip for text-only modality."""
    data = _node_output(state, "orchestrator") or {}
    try:
        orch = OrchestratorOutput.model_validate(data)
    except Exception:
        return True       # safe default: scan
    return orch.modality in {"image", "video", "mixed"}


def route_to_text_guard(state) -> bool:
    """Text guard fires when orchestrator or fast_screen indicates text content."""
    orch_data = _node_output(state, "orchestrator") or {}
    if orch_data.get("modality") in {"text", "mixed"} or orch_data.get("needs_text_guard"):
        return True
    fs_data = _node_output(state, "fast_screen") or {}
    return bool(fs_data.get("has_text"))


def needs_deep_review(state) -> bool:
    """Fast screen → deep review: threshold-driven, possibly Memory-adjusted."""
    fs_data = _node_output(state, "fast_screen")
    if fs_data is None:
        return False
    try:
        fs = FastScreenOutput.model_validate(fs_data)
    except Exception:
        return False

    orch_data = _node_output(state, "orchestrator") or {}
    threshold = float(orch_data.get("effective_threshold", 75.0))

    if fs.max_confidence >= threshold:
        return True
    if any(lab.get("Name") in HIGH_RISK_LABEL_NAMES for lab in fs.labels):
        return True
    if 60 <= fs.max_confidence < threshold and fs.trigger_deep_review:
        return True
    return False


def _required_predecessors(state) -> list[str]:
    """Compute which nodes MUST complete before decision can fire."""
    required = ["orchestrator"]
    orch_data = _node_output(state, "orchestrator") or {}
    modality = orch_data.get("modality", "image")

    if modality != "text":
        required.append("fast_screen")

    if _completed(state, "fast_screen") and needs_deep_review(state):
        required.append("deep_review")

    if route_to_text_guard(state):
        required.append("text_guard")

    return required


def can_decide(state) -> bool:
    """AND-style gate: only allow decision when all *required* nodes are done."""
    for node_id in _required_predecessors(state):
        if not _completed(state, node_id):
            return False
    return True


# --------------------------------------------------------------- decision routing
# Two decision nodes: `decision_light` (Haiku, fast path for low-risk content)
# vs `decision_heavy` (Sonnet, full reasoning). Both AND-gated by can_decide().

def _is_low_risk(state) -> bool:
    """True when orchestrator says low-risk AND no signal from upstream nodes."""
    orch = _node_output(state, "orchestrator") or {}
    if orch.get("prior_risk", "medium") != "low":
        return False
    fs = _node_output(state, "fast_screen") or {}
    if float(fs.get("max_confidence") or 0) > 0:
        return False
    if fs.get("has_text"):
        return False
    # If deep_review got triggered, never go light
    if needs_deep_review(state):
        return False
    if route_to_text_guard(state):
        return False
    return True


def route_to_decision_light(state) -> bool:
    """Only fire decision_light when can_decide AND content is low-risk."""
    return can_decide(state) and _is_low_risk(state)


def route_to_decision_heavy(state) -> bool:
    """Fire decision_heavy for everything that can_decide but isn't low-risk."""
    return can_decide(state) and not _is_low_risk(state)

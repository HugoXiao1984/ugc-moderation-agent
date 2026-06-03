"""Graph condition-edge unit tests using a fake GraphState."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from ugc_moderation.graph.conditions import (
    _parse_last_json_blob,
    can_decide,
    needs_deep_review,
    route_to_fast_screen,
    route_to_text_guard,
)


class _FakeStatus:
    COMPLETED = "COMPLETED"


@dataclass
class _FakeNode:
    output: str
    status: str = _FakeStatus.COMPLETED


@dataclass
class _FakeState:
    results: dict = field(default_factory=dict)


@pytest.fixture(autouse=True)
def _patch_status(monkeypatch):
    """Conditions import `Status` from strands; patch it to match FakeNode."""
    import ugc_moderation.graph.conditions as cond
    monkeypatch.setattr(cond, "Status", SimpleNamespace(COMPLETED="COMPLETED"))


# -------- _parse_last_json_blob --------------------------------------------

def test_parse_last_json_blob_picks_last():
    text = 'prefix {"a": 1} middle {"b": 2, "c": [1,2]} tail'
    assert _parse_last_json_blob(text) == {"b": 2, "c": [1, 2]}


def test_parse_last_json_blob_handles_nested():
    text = 'noise {"outer": {"inner": 42}, "arr": [1,2]}'
    assert _parse_last_json_blob(text) == {"outer": {"inner": 42}, "arr": [1, 2]}


def test_parse_last_json_blob_empty_when_no_json():
    assert _parse_last_json_blob("no json here") == {}


# -------- route_to_fast_screen ---------------------------------------------

def _state_with(orch_json: dict, fs_json: dict | None = None) -> _FakeState:
    results = {"orchestrator": _FakeNode(output=json.dumps(orch_json))}
    if fs_json is not None:
        results["fast_screen"] = _FakeNode(output=json.dumps(fs_json))
    return _FakeState(results=results)


def test_route_to_fast_screen_image_yes():
    state = _state_with({"modality": "image", "jurisdiction": "CN", "effective_threshold": 75.0})
    assert route_to_fast_screen(state) is True


def test_route_to_fast_screen_text_no():
    state = _state_with({"modality": "text", "jurisdiction": "CN", "effective_threshold": 75.0})
    assert route_to_fast_screen(state) is False


# -------- needs_deep_review -------------------------------------------------

def test_needs_deep_review_triggered_by_high_confidence():
    fs = {"max_confidence": 82.0, "labels": [{"Name": "Suggestive", "Confidence": 82}], "has_text": False, "trigger_deep_review": False}
    state = _state_with({"modality": "image", "jurisdiction": "CN", "effective_threshold": 75.0}, fs)
    assert needs_deep_review(state) is True


def test_needs_deep_review_triggered_by_high_risk_label():
    fs = {"max_confidence": 30.0, "labels": [{"Name": "Hate Symbols", "Confidence": 30}], "has_text": False, "trigger_deep_review": False}
    state = _state_with({"modality": "image", "jurisdiction": "CN", "effective_threshold": 75.0}, fs)
    assert needs_deep_review(state) is True


def test_needs_deep_review_skipped_when_safe():
    fs = {"max_confidence": 20.0, "labels": [{"Name": "Alcohol", "Confidence": 20}], "has_text": False, "trigger_deep_review": False}
    state = _state_with({"modality": "image", "jurisdiction": "CN", "effective_threshold": 75.0}, fs)
    assert needs_deep_review(state) is False


def test_needs_deep_review_with_dynamic_threshold_widening():
    # Memory widened threshold to 85; a 78 label should NOT trigger now
    fs = {"max_confidence": 78.0, "labels": [{"Name": "Suggestive", "Confidence": 78}], "has_text": False, "trigger_deep_review": False}
    state = _state_with({"modality": "image", "jurisdiction": "CN", "effective_threshold": 85.0}, fs)
    assert needs_deep_review(state) is False


# -------- route_to_text_guard -----------------------------------------------

def test_route_text_guard_when_modality_mixed():
    state = _state_with({"modality": "mixed", "jurisdiction": "CN", "effective_threshold": 75.0})
    assert route_to_text_guard(state) is True


def test_route_text_guard_when_fast_screen_has_text():
    fs = {"max_confidence": 10.0, "labels": [], "has_text": True, "trigger_deep_review": False}
    state = _state_with({"modality": "image", "jurisdiction": "CN", "effective_threshold": 75.0}, fs)
    assert route_to_text_guard(state) is True


# -------- can_decide AND gate -----------------------------------------------

def test_can_decide_blocked_when_fast_screen_missing():
    state = _state_with({"modality": "image", "jurisdiction": "CN", "effective_threshold": 75.0})
    assert can_decide(state) is False


def test_can_decide_allows_when_all_required_done():
    fs = {"max_confidence": 20.0, "labels": [], "has_text": False, "trigger_deep_review": False}
    state = _state_with({"modality": "image", "jurisdiction": "CN", "effective_threshold": 75.0}, fs)
    assert can_decide(state) is True


def test_can_decide_waits_for_deep_review_when_triggered():
    # High conf triggers deep review; deep_review not yet completed → cannot decide
    fs = {"max_confidence": 85.0, "labels": [{"Name": "Suggestive", "Confidence": 85}], "has_text": False, "trigger_deep_review": True}
    state = _state_with({"modality": "image", "jurisdiction": "CN", "effective_threshold": 75.0}, fs)
    assert can_decide(state) is False

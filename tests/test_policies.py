"""Jurisdiction policy scripts — unit tests.

These are pure functions, no AWS dependencies. Verifies that identical input
signals yield *different* decisions across CN/EU/US policies — the core
demo narrative.
"""
from __future__ import annotations

from ugc_moderation.policies import cn, eu, us

# -------- helpers ----------------------------------------------------------

def _labels(*pairs: tuple[str, float]) -> list[dict]:
    return [{"Name": n, "Confidence": c} for n, c in pairs]


# -------- CN specifics -----------------------------------------------------

def test_cn_red_line_keyword_denies_immediately():
    r = cn.evaluate({
        "labels": [],
        "nova_reasoning": "画面包含反政府标语和口号",
        "guardrail": {},
    })
    assert r.decision == "deny"
    assert r.escalation_needed is True
    assert any("红线" in rule or "网络安全法" in rule for rule in r.violated_rules)


def test_cn_suggestive_above_strict_threshold_denies():
    r = cn.evaluate({
        "labels": _labels(("Suggestive", 60)),
        "nova_reasoning": "",
        "guardrail": {},
    })
    assert r.decision == "deny"


def test_cn_clean_allow():
    r = cn.evaluate({"labels": [], "nova_reasoning": "", "guardrail": {}})
    assert r.decision == "allow"


# -------- EU specifics -----------------------------------------------------

def test_eu_child_strict_threshold():
    # Minor detected + moderate Suggestive → should deny (child strict 20)
    r = eu.evaluate({
        "labels": _labels(("Minor", 80), ("Suggestive", 30)),
        "nova_reasoning": "",
        "guardrail": {},
    })
    assert r.decision == "deny"
    assert any("GDPR" in rule or "DSA" in rule or "未成年" in rule for rule in r.violated_rules)


def test_eu_allow_includes_reasoning_for_dsa_transparency():
    r = eu.evaluate({"labels": [], "nova_reasoning": "", "guardrail": {}})
    assert r.decision == "allow"
    # DSA transparency: reasoning_cn must be non-trivial
    assert len(r.reasoning_cn) > 10


# -------- US specifics -----------------------------------------------------

def test_us_lenient_suggestive_even_at_80_still_passes():
    # Suggestive 85 < US threshold 90 → allow
    r = us.evaluate({
        "labels": _labels(("Suggestive", 85)),
        "nova_reasoning": "",
        "guardrail": {},
    })
    assert r.decision == "allow"


def test_us_coppa_child_strict():
    r = us.evaluate({
        "labels": _labels(("Minor", 80), ("Suggestive", 20)),
        "nova_reasoning": "",
        "guardrail": {},
    })
    assert r.decision == "deny"
    assert any("COPPA" in rule for rule in r.violated_rules)


def test_us_fosta_sesta_keyword():
    r = us.evaluate({
        "labels": [],
        "nova_reasoning": "",
        "ocr_text": "click here for escort service",
        "guardrail": {},
    })
    assert r.decision == "deny"
    assert any("FOSTA" in rule for rule in r.violated_rules)


# -------- Cross-jurisdiction divergence (the headline demo) ----------------

def test_suggestive_70_diverges_across_jurisdictions():
    """Same signal (Suggestive at 70%) → CN deny, EU allow, US allow."""
    signals = {
        "labels": _labels(("Suggestive", 70)),
        "nova_reasoning": "",
        "guardrail": {},
    }
    assert cn.evaluate(signals).decision == "deny"       # CN strict: 55
    assert eu.evaluate(signals).decision == "allow"      # EU: 75
    assert us.evaluate(signals).decision == "allow"      # US: 90


def test_violence_72_diverges():
    signals = {
        "labels": _labels(("Violence", 72)),
        "nova_reasoning": "",
        "guardrail": {},
    }
    assert cn.evaluate(signals).decision == "deny"       # CN 55
    assert eu.evaluate(signals).decision == "deny"       # EU 70
    assert us.evaluate(signals).decision == "allow"      # US 85

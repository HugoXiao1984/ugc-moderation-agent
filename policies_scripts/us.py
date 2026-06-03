"""US jurisdiction — First Amendment lenience + COPPA strictness.

Adult content is broadly tolerated; under-13 signals trigger the strictest arm.
Section 230 transparency reports tracked via reasoning_cn.
"""
from __future__ import annotations

from common import PolicyResult, any_label_above, normalize_labels

HIGH_RISK_LABELS_US: dict[str, float] = {
    "Explicit Nudity": 80,
    "Non-Explicit Nudity of Intimate parts and Kissing": 85,
    "Suggestive": 90,
    "Violence": 85,
    "Graphic Violence": 75,
    "Hate Symbols": 50,
    "Visually Disturbing": 85,
}

CHILD_SIGNAL_LABELS = {"Minor", "Child", "Baby", "Kid"}
COPPA_STRICT_THRESHOLDS = {
    "Explicit Nudity": 10,
    "Non-Explicit Nudity of Intimate parts and Kissing": 15,
    "Suggestive": 15,
    "Violence": 35,
}

# FOSTA-SESTA
TRAFFICKING_KEYWORDS = {"escort", "trafficking", "prostitution"}


def evaluate(signals: dict) -> PolicyResult:
    labels = normalize_labels(signals.get("labels", []))
    nova_text = (signals.get("nova_reasoning", "") + " " + signals.get("ocr_text", "")).lower()
    gr = signals.get("guardrail") or {}

    # 1) COPPA: 未成年先行
    child_present = any(labels.get(c, 0) > 50 for c in CHILD_SIGNAL_LABELS)
    if child_present:
        hits = any_label_above(labels, COPPA_STRICT_THRESHOLDS)
        if hits:
            rules = ["COPPA 15 USC §6501", "Child Safety"] + \
                    [f"{n} {c:.1f}% > {t}%" for n, c, t in hits]
            return PolicyResult(
                decision="deny",
                violated_rules=rules,
                reasoning_cn=f"检测到未成年特征 + {hits[0][0]} 风险，依据 COPPA 拒绝发布并升级 NCMEC 报告流程。",
                confidence=0.97,
                escalation_needed=True,
                thresholds_used={n: t for n, _, t in hits},
            )

    # 2) FOSTA-SESTA
    if any(k in nova_text for k in TRAFFICKING_KEYWORDS):
        return PolicyResult(
            decision="deny",
            violated_rules=["FOSTA-SESTA (18 USC §1591, §2421A)"],
            reasoning_cn="内容涉及疑似人口贩卖相关词汇，依据 FOSTA-SESTA 拒绝。",
            confidence=0.9,
            escalation_needed=True,
        )

    # 3) 通用标签（阈值宽松，体现第一修正案原则）
    hits = any_label_above(labels, HIGH_RISK_LABELS_US)
    if hits:
        rules = ["Platform Community Standards"] + [f"{n} {c:.1f}% > {t}%" for n, c, t in hits]
        top = max(hits, key=lambda h: h[1] - h[2])
        return PolicyResult(
            decision="human_review",
            violated_rules=rules,
            reasoning_cn=f"{top[0]} 超过美国宽松阈值 {top[2]}%，转人审（美国法域保留平台自治决策空间）。",
            confidence=0.75,
            escalation_needed=False,
            thresholds_used={n: t for n, _, t in hits},
        )

    if gr.get("action") == "GUARDRAIL_INTERVENED":
        return PolicyResult(
            decision="human_review",
            violated_rules=["Platform Guardrail"],
            reasoning_cn="文本护栏拦截，转人审以尊重第一修正案言论自由边界。",
            confidence=0.65,
            escalation_needed=False,
        )

    return PolicyResult(
        decision="allow",
        violated_rules=[],
        reasoning_cn="美国法域审核通过：未触发 COPPA、FOSTA-SESTA 或平台标准阈值。",
        confidence=0.8,
        escalation_needed=False,
        thresholds_used=HIGH_RISK_LABELS_US,
    )

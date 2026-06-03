"""EU jurisdiction — DSA transparency + GDPR child protection.

DSA requires reasoned decisions even for allowed content; we always populate
reasoning_cn. Age-related signals trigger the strictest arm.
"""
from __future__ import annotations

from common import PolicyResult, any_label_above, normalize_labels

HIGH_RISK_LABELS_EU: dict[str, float] = {
    "Explicit Nudity": 60,
    "Non-Explicit Nudity of Intimate parts and Kissing": 70,
    "Suggestive": 75,
    "Violence": 70,
    "Graphic Violence": 60,
    "Hate Symbols": 40,
    "Visually Disturbing": 75,
    "Drugs & Tobacco Paraphernalia": 65,
}

# GDPR / 儿童保护专项
CHILD_SIGNAL_LABELS = {"Minor", "Child", "Baby", "Kid"}
CHILD_STRICT_THRESHOLDS = {
    "Explicit Nudity": 15,
    "Non-Explicit Nudity of Intimate parts and Kissing": 25,
    "Suggestive": 20,
    "Violence": 40,
}


def evaluate(signals: dict) -> PolicyResult:
    labels = normalize_labels(signals.get("labels", []))
    nova_text = signals.get("nova_reasoning", "")
    gr = signals.get("guardrail") or {}

    # 1) 儿童保护优先（GDPR + DSA Art.28）
    child_present = any(labels.get(c, 0) > 50 for c in CHILD_SIGNAL_LABELS)
    if child_present:
        hits = any_label_above(labels, CHILD_STRICT_THRESHOLDS)
        if hits:
            rules = ["GDPR Art.8 (Child)", "DSA Art.28 - 未成年保护"] + \
                    [f"{name} {conf:.1f}% > {thr}%" for name, conf, thr in hits]
            return PolicyResult(
                decision="deny",
                violated_rules=rules,
                reasoning_cn=f"检测到未成年相关特征，同时命中 {hits[0][0]} 风险标签，依据 GDPR 及 DSA 未成年保护条款拒绝发布。",
                confidence=0.95,
                escalation_needed=True,
                thresholds_used={n: t for n, _, t in hits},
            )

    # 2) 标签阈值
    hits = any_label_above(labels, HIGH_RISK_LABELS_EU)
    if hits:
        rules = ["DSA Art.16 - 非法内容通告机制"] + [f"{n} {c:.1f}% > {t}%" for n, c, t in hits]
        top = max(hits, key=lambda h: h[1] - h[2])
        return PolicyResult(
            decision="deny",
            violated_rules=rules,
            reasoning_cn=f"依据欧盟 DSA 及相关内容法规，{top[0]} 标签超过阈值，拒绝发布。",
            confidence=0.88,
            escalation_needed=False,
            thresholds_used={n: t for n, _, t in hits},
        )

    # 3) Guardrail
    if gr.get("action") == "GUARDRAIL_INTERVENED":
        return PolicyResult(
            decision="human_review",
            violated_rules=["Bedrock Guardrail blocked text"],
            reasoning_cn="文本被护栏拦截，依据 DSA 透明度原则转人审并附具体拦截原因。",
            confidence=0.7,
            escalation_needed=True,
        )

    # DSA 透明度：allow 也带 reasoning
    return PolicyResult(
        decision="allow",
        violated_rules=[],
        reasoning_cn="经 DSA + GDPR 欧盟法域审核，未命中任何标签/关键词/护栏规则，允许发布（已根据 DSA Art.17 生成可审计推理）。",
        confidence=0.82,
        escalation_needed=False,
        thresholds_used=HIGH_RISK_LABELS_EU,
    )

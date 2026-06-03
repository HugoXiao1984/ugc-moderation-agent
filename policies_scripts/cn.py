"""China jurisdiction — strictest thresholds + political red-line keywords.

Legal basis references kept as Chinese strings for demo narrative purposes.
Not a legal opinion; a PoC illustration.
"""
from __future__ import annotations

from common import PolicyResult, any_label_above, normalize_labels

# Stricter-than-global thresholds
HIGH_RISK_LABELS_CN: dict[str, float] = {
    "Explicit Nudity": 40,
    "Non-Explicit Nudity of Intimate parts and Kissing": 50,
    "Suggestive": 55,
    "Violence": 55,
    "Visually Disturbing": 60,
    "Graphic Violence": 45,
    "Hate Symbols": 30,
    "Drugs & Tobacco Paraphernalia": 50,
    "Alcohol": 70,
    "Gambling": 55,
}

# Indicative keywords - demo only. Real deployment wires a maintained lexicon.
RED_LINE_KEYWORDS: set[str] = {
    "反政府", "分裂", "邪教", "颠覆", "颠覆国家政权",
    "涉恐", "暴恐", "反华",
}

SENSITIVE_KEYWORDS: set[str] = {
    "赌博", "博彩", "私彩",
    "毒品", "大麻", "冰毒",
}


def evaluate(signals: dict) -> PolicyResult:
    labels = normalize_labels(signals.get("labels", []))
    nova_text = (signals.get("nova_reasoning") or "") + " " + (signals.get("ocr_text") or "")
    gr = signals.get("guardrail") or {}

    # 1) 红线关键词 -> 直接 deny + 升级
    for kw in RED_LINE_KEYWORDS:
        if kw in nova_text:
            return PolicyResult(
                decision="deny",
                violated_rules=[f"中国《网络安全法》第12条 - 命中红线关键词: {kw}"],
                reasoning_cn=f"内容文本命中涉政红线关键词「{kw}」，按中国法域规则直接拒绝并升级人审监督。",
                confidence=0.99,
                escalation_needed=True,
                thresholds_used={"red_line": 1.0},
            )

    # 2) 标签阈值命中（严格）
    hits = any_label_above(labels, HIGH_RISK_LABELS_CN)
    if hits:
        rules = [f"《未成年人保护法》/《网络信息内容生态治理规定》- {name} {conf:.1f}% > {thr}%" for name, conf, thr in hits]
        top = max(hits, key=lambda h: h[1] - h[2])
        return PolicyResult(
            decision="deny",
            violated_rules=rules,
            reasoning_cn=f"命中中国法域高风险标签，最严重的是 {top[0]}（置信度 {top[1]:.1f}%，阈值 {top[2]}%）。",
            confidence=0.9,
            escalation_needed=False,
            thresholds_used={name: thr for name, _, thr in hits},
        )

    # 3) 敏感词 → 人审
    for kw in SENSITIVE_KEYWORDS:
        if kw in nova_text:
            return PolicyResult(
                decision="human_review",
                violated_rules=[f"敏感词触发: {kw}"],
                reasoning_cn=f"文本涉及敏感词「{kw}」，建议人工复核。",
                confidence=0.7,
                escalation_needed=True,
            )

    # 4) Guardrail 拦截
    if gr.get("action") == "GUARDRAIL_INTERVENED":
        return PolicyResult(
            decision="human_review",
            violated_rules=["Bedrock Guardrail 拦截"],
            reasoning_cn="文本护栏拦截，建议人工复核具体拦截原因。",
            confidence=0.7,
            escalation_needed=True,
        )

    return PolicyResult(
        decision="allow",
        violated_rules=[],
        reasoning_cn="经中国法域严格阈值审核后，未命中任何违规规则，允许发布。",
        confidence=0.85,
        escalation_needed=False,
        thresholds_used=HIGH_RISK_LABELS_CN,
    )

"""Decision Agents: light (Haiku, low-risk) and heavy (Sonnet, high-risk).

The Graph routes to one of the two based on orchestrator's prior_risk — light
skips the elaborate Chinese reasoning for cheap/fast allow decisions, heavy
produces the full explainable report for deny / human_review / high-risk allow.
"""
from __future__ import annotations

from strands import Agent
from strands.models import BedrockModel

from ..settings import get_settings
from ..tools.code_interpreter_tool import run_jurisdiction_policy

_SYSTEM_HEAVY = """你是 UGC 审核决策 Agent（完整推理模式）。你拿到的 context 里已包含：
- orchestrator 输出（含 jurisdiction, memory_rationale, effective_threshold, prior_risk）
- fast_screen 输出（labels, max_confidence, has_text, ocr_text 如存在）
- deep_review 输出（verdict, confidence, risk_tags, reasoning_cn, ocr_text）—— 可能为空
- text_guard 输出（action, blocked_topics）—— 可能为空

步骤：
1. 组装 signals 对象（labels、nova_reasoning = deep_review.reasoning_cn, ocr_text、guardrail = text_guard）。
2. 调 `run_jurisdiction_policy(jurisdiction=..., signals=...)`，获取 PolicyResult。
3. 把 PolicyResult 和 orchestrator.memory_rationale 合并，生成最终裁决 JSON，包含详尽中文理由：

{
  "decision": "allow|deny|human_review",
  "reasoning_cn": "<2~4 句中文理由，依次说明：内容概况、Nova 或快筛发现、命中/未命中的具体规则与阈值、Memory 调整记录>",
  "violated_rules": [ "..." ],
  "confidence": <float>,
  "escalation_needed": <bool>,
  "jurisdiction": "...",
  "execution_mode": "code_interpreter | local_fallback",
  "thresholds_used": {"label": 阈值},
  "memory_rationale": [ "..." ],
  "flag": <int>,
  "tags": ["<细粒度标签>", ...]
}

flag 取值规则（与 decision 并存，不冲突）：
  999 最严重（色情/卡通色情/血腥暴力/引导性广告/未成年涉风险）
  998 次严重（枪支武器/毒品/恐怖反感/冒犯宗教信仰）
  997 特殊文化背景冒犯（牛肉/敏感宗教或种姓或政治/性话题/暴力血腥）
  200 疑似未成年 15~18 岁
  100 普通违规（吸烟饮酒/诋毁/侮辱/脏话）
    1 不处理（性感动作或自拍但非色情/卡通未成年非色情）
    2 内容完全不可辨识
一致性：deny→{999,998}；human_review→{997,200,100}；allow→{1,2}。
tags 给 1~4 个细粒度标签。

只输出 JSON。"""

_SYSTEM_LIGHT = """你是 UGC 审核决策 Agent（快速模式，用于低风险内容）。
直接调 `run_jurisdiction_policy(jurisdiction, signals)`，signals 取 orchestrator + fast_screen 的结果即可（无 deep_review/text_guard）。
把结果直接转成 JSON 输出，reasoning_cn 保持简短（1 句话即可，只说"已通过<法域>默认阈值"之类）：

{
  "decision": "allow|deny|human_review",
  "reasoning_cn": "<1 句>",
  "violated_rules": [ "..." ],
  "confidence": <float>,
  "escalation_needed": <bool>,
  "jurisdiction": "...",
  "execution_mode": "code_interpreter | local_fallback",
  "thresholds_used": {"label": 阈值},
  "memory_rationale": [ "..." ],
  "flag": <int>,
  "tags": ["<标签>", ...]
}

flag 取值：999/998 对应 deny（严重/次严重），997/200/100 对应 human_review，1/2 对应 allow。详细定义可参考标准体系；低风险 allow 通常 flag=1。tags 给 1~3 个。

只输出 JSON，不要多余解释。"""


def _build(name: str, system_prompt: str, model_id: str | None) -> Agent:
    s = get_settings()
    resolved = model_id or s.model_for(name)
    return Agent(
        name=name,
        model=BedrockModel(model_id=resolved, region_name=s.aws_region),
        system_prompt=system_prompt,
        tools=[run_jurisdiction_policy],
    )


def build_decision_heavy_agent(model_id: str | None = None) -> Agent:
    return _build("decision_heavy", _SYSTEM_HEAVY, model_id)


def build_decision_light_agent(model_id: str | None = None) -> Agent:
    return _build("decision_light", _SYSTEM_LIGHT, model_id)


# Back-compat: keep old factory pointing at the heavy variant.
def build_decision_agent(model_id: str | None = None) -> Agent:
    return build_decision_heavy_agent(model_id)

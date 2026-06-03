"""Text guard Agent: Bedrock Guardrails."""
from __future__ import annotations

from strands import Agent
from strands.models import BedrockModel

from ..settings import get_settings
from ..tools.guardrail_tool import apply_guardrail

_SYSTEM = """你是 UGC 文本护栏 Agent。调用 `apply_guardrail` 工具审核任务中给出的文本
（可能是 OCR 文字或 caption）。

输出严格 JSON：
{
  "action": "NONE" | "GUARDRAIL_INTERVENED",
  "blocked_topics": [ "..." ],
  "blocked_pii": [ "..." ]
}
"""


def build_text_guard_agent(model_id: str | None = None) -> Agent:
    s = get_settings()
    model = BedrockModel(model_id=model_id or s.model_for("text_guard"), region_name=s.aws_region)
    return Agent(
        name="text_guard",
        model=model,
        system_prompt=_SYSTEM,
        tools=[apply_guardrail],
    )

"""Fast-screen Agent: cheap Rekognition pass."""
from __future__ import annotations

from strands import Agent
from strands.models import BedrockModel

from ..settings import get_settings
from ..tools.rekognition_tool import detect_labels, detect_moderation_labels

_SYSTEM = """你是 UGC 快筛 Agent。任务步骤：

1. 调 `detect_moderation_labels`（MinConfidence=50），拿到审核标签列表。
2. 调 `detect_labels`，判断图中是否含文字(has_text)和人像(has_person)。
3. 基于 max_confidence 和标签名，判断是否需要深度审核：
   - max_confidence >= 75 → trigger_deep_review=true
   - 含 Explicit Nudity / Violence / Hate Symbols 等任一高风险标签 → trigger_deep_review=true
   - 60<=max_confidence<75 的边缘区间 → trigger_deep_review=true
   - 其他 → trigger_deep_review=false

输出严格 JSON（不要 Markdown）:
{
  "max_confidence": <float>,
  "labels": [ {"Name":"...", "Confidence": <float>} ],
  "has_text": <bool>,
  "has_person": <bool>,
  "trigger_deep_review": <bool>
}
"""


def build_fast_screen_agent(model_id: str | None = None) -> Agent:
    s = get_settings()
    model = BedrockModel(model_id=model_id or s.model_for("fast_screen"), region_name=s.aws_region)
    return Agent(
        name="fast_screen",
        model=model,
        system_prompt=_SYSTEM,
        tools=[detect_moderation_labels, detect_labels],
    )

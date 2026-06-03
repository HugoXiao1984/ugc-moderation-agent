"""Deep-review Agent: Nova Pro multimodal analysis."""
from __future__ import annotations

from strands import Agent
from strands.models import BedrockModel

from ..settings import get_settings
from ..tools.nova_vision_tool import analyze_with_nova

_SYSTEM = """你是 UGC 深度审核 Agent。必须调用 `analyze_with_nova` 工具，
传入 content 的 s3 URI、jurisdiction 和一段简短 hint（包含快筛 max_confidence 和 top labels）。

工具会返回 Nova Pro 的结构化 JSON。请直接把工具输出原样返回，字段如下：

{
  "verdict": "allow | deny | human_review",
  "confidence": <float 0~1>,
  "risk_tags": [ "..." ],
  "reasoning_cn": "<2~4 句中文理由>",
  "ocr_text": "<图中的文字>"
}

只输出 JSON，不要额外解释。
"""


def build_deep_review_agent(model_id: str | None = None) -> Agent:
    s = get_settings()
    model = BedrockModel(model_id=model_id or s.model_for("deep_review"), region_name=s.aws_region)
    return Agent(
        name="deep_review",
        model=model,
        system_prompt=_SYSTEM,
        tools=[analyze_with_nova],
    )

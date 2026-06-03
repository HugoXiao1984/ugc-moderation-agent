"""Orchestrator Agent: modality + jurisdiction + Memory recall."""
from __future__ import annotations

from strands import Agent
from strands.models import BedrockModel

from ..settings import get_settings
from ..tools.memory_tool import recall_similar_cases
from ..tools.s3_tool import fetch_image_metadata

_SYSTEM = """你是 UGC 审核编排 Agent。收到一条待审核内容后，你必须：

1. 调 `fetch_image_metadata` 获取内容元数据（若为图像 URI）。
2. 调 `recall_similar_cases` 查询 AgentCore Memory 中相似的历史误判案例：
   - 查询语句用自然语言描述待审内容（不超过一句话）。
   - 法域参数使用任务中给出的 jurisdiction。
3. 根据召回结果调整 effective_threshold：
   - 相似历史误判(corrected_decision=="allow") → 放宽到 85
   - 相似历史漏判(corrected_decision=="deny")  → 收紧到 65
   - 未命中或相关度低 → 保持默认 75
4. 判断 modality (image|video|text|mixed)、prior_risk (low|medium|high)、是否需要文本护栏。

最后输出**仅一段 JSON**（不要 Markdown/解释），字段严格遵守：

{
  "modality": "...",
  "jurisdiction": "...",
  "prior_risk": "...",
  "effective_threshold": <float>,
  "memory_hits": [ {"memory_id":"...", "relevance_score":<float>, "corrected_decision":"..."} ],
  "memory_rationale": ["阈值从 75 调整到 85，依据 ..."],
  "routing_hint": "一句话说明下游节点应当注意什么",
  "needs_text_guard": <bool>
}
"""


def build_orchestrator_agent(model_id: str | None = None) -> Agent:
    s = get_settings()
    model = BedrockModel(model_id=model_id or s.model_for("orchestrator"), region_name=s.aws_region)
    return Agent(
        name="orchestrator",
        model=model,
        system_prompt=_SYSTEM,
        tools=[fetch_image_metadata, recall_similar_cases],
    )

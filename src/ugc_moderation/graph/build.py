"""Wire the moderation Graph (6 nodes, AND-gated decision split into light/heavy)."""
from __future__ import annotations

from strands.multiagent.graph import GraphBuilder

from ..agents import (
    build_decision_heavy_agent,
    build_decision_light_agent,
    build_deep_review_agent,
    build_fast_screen_agent,
    build_orchestrator_agent,
    build_text_guard_agent,
)
from .conditions import (
    needs_deep_review,
    route_to_decision_heavy,
    route_to_decision_light,
    route_to_fast_screen,
    route_to_text_guard,
)


def build_moderation_graph():
    builder = GraphBuilder()
    builder.add_node(build_orchestrator_agent(), "orchestrator")
    builder.add_node(build_fast_screen_agent(), "fast_screen")
    builder.add_node(build_deep_review_agent(), "deep_review")
    builder.add_node(build_text_guard_agent(), "text_guard")
    builder.add_node(build_decision_light_agent(), "decision_light")
    builder.add_node(build_decision_heavy_agent(), "decision_heavy")

    # Flow
    builder.add_edge("orchestrator", "fast_screen", condition=route_to_fast_screen)
    builder.add_edge("fast_screen", "deep_review", condition=needs_deep_review)
    builder.add_edge("orchestrator", "text_guard", condition=route_to_text_guard)
    builder.add_edge("fast_screen", "text_guard", condition=route_to_text_guard)

    # Two decision paths — exactly one fires (guards are mutually exclusive).
    for upstream in ("fast_screen", "deep_review", "text_guard", "orchestrator"):
        builder.add_edge(upstream, "decision_light", condition=route_to_decision_light)
        builder.add_edge(upstream, "decision_heavy", condition=route_to_decision_heavy)

    builder.set_entry_point("orchestrator")
    builder.set_execution_timeout(180)
    return builder.build()


def build_moderation_task(content_s3_uri: str, jurisdiction: str, ocr_text: str = "") -> str:
    extra = f"\n现有 OCR/caption 文本: {ocr_text}" if ocr_text else ""
    return (
        f"请审核内容 {content_s3_uri}，声明法域 {jurisdiction}。"
        f"请按系统提示调用工具并输出 JSON。{extra}"
    )

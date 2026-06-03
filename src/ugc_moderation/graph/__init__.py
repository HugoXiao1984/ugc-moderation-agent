"""Graph package.

`build_moderation_graph` / `build_moderation_task` import Strands which
requires heavy deps; lazy-load so lightweight consumers (tests, scripts)
can import just `.conditions` / `.state`.
"""
from __future__ import annotations

from .state import (
    DecisionOutput,
    DeepReviewOutput,
    FastScreenOutput,
    ModerationReport,
    OrchestratorOutput,
    TextGuardOutput,
)


def build_moderation_graph(*args, **kwargs):
    from .build import build_moderation_graph as _real
    return _real(*args, **kwargs)


def build_moderation_task(*args, **kwargs):
    from .build import build_moderation_task as _real
    return _real(*args, **kwargs)


__all__ = [
    "build_moderation_graph",
    "build_moderation_task",
    "ModerationReport",
    "OrchestratorOutput",
    "FastScreenOutput",
    "DeepReviewOutput",
    "TextGuardOutput",
    "DecisionOutput",
]

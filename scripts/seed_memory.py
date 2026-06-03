"""Seed AgentCore Memory with a handful of plausible misjudgment cases.

Makes Demo Tab 3 feel realistic immediately — upload a gym/muscle image, and
orchestrator will recall the seeded misjudgment and widen the threshold.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ugc_moderation.settings import get_settings
from ugc_moderation.tools.memory_tool import record_misjudgment

SEEDS = [
    # CN: gym muscle shots repeatedly flagged as Suggestive
    {
        "case_id": "seed-cn-001",
        "original_decision": "deny",
        "corrected_decision": "allow",
        "signals_summary": "健身房男士举重特写，肌肉线条明显，无裸露。快筛 Suggestive 78%，被误判。",
        "jurisdiction": "CN",
    },
    {
        "case_id": "seed-cn-002",
        "original_decision": "deny",
        "corrected_decision": "allow",
        "signals_summary": "瑜伽女士拉伸动作，运动紧身衣，快筛 Suggestive 72%，被误判。",
        "jurisdiction": "CN",
    },
    # CN: art class nude sketch — actual violation
    {
        "case_id": "seed-cn-003",
        "original_decision": "allow",
        "corrected_decision": "deny",
        "signals_summary": "油画人体写生，快筛 Explicit Nudity 42%，阈值 40 边缘未触发，被漏判。",
        "jurisdiction": "CN",
    },
    # EU: violent video game screenshots allowed (game industry exemption)
    {
        "case_id": "seed-eu-001",
        "original_decision": "deny",
        "corrected_decision": "allow",
        "signals_summary": "电子游戏战斗截图，UI 可见，Violence 71%，被误判为现实暴力。",
        "jurisdiction": "EU",
    },
    # US: same gym content — already allowed at baseline, recorded as reinforcement
    {
        "case_id": "seed-us-001",
        "original_decision": "human_review",
        "corrected_decision": "allow",
        "signals_summary": "健身举重 Suggestive 77%，美国阈值 90 内合规，人审确认允许。",
        "jurisdiction": "US",
    },
]


def main() -> int:
    s = get_settings()
    if not s.memory_id:
        print("MEMORY_ID not set in env — run scripts/create_memory.py first.")
        return 1

    print(f"Seeding Memory {s.memory_id} with {len(SEEDS)} cases...")
    ok_count = 0
    for seed in SEEDS:
        r = record_misjudgment(**seed)
        status = "OK" if r.get("ok") else f"FAIL ({r.get('reason','')})"
        print(f"  [{seed['jurisdiction']}] {seed['case_id']}: {status}")
        if r.get("ok"):
            ok_count += 1
    print(f"Done. {ok_count}/{len(SEEDS)} succeeded.")
    return 0 if ok_count == len(SEEDS) else 2


if __name__ == "__main__":
    raise SystemExit(main())

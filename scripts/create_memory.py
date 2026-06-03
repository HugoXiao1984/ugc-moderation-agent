"""One-shot script: create the AgentCore Memory resource.

Usage:
    uv run python scripts/create_memory.py
Writes MEMORY_ID to stdout; paste into .env.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ugc_moderation.memory.setup import create_memory_resource  # noqa: E402


def main() -> int:
    out = create_memory_resource()
    print("\n=== Memory resource created ===")
    print(f"MEMORY_ID={out['memory_id']}")
    print("Paste the above line into .env")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

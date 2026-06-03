"""Pretty-print the latest pipeline trace from /tmp/ugc_moderation_trace.jsonl.

Usage:
    uv run python scripts/show_trace.py            # latest case
    uv run python scripts/show_trace.py --all      # every case in the file
    uv run python scripts/show_trace.py --case case-xxxxxxxx
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path


TRACE = Path(os.environ.get("UGC_TRACE_FILE", "/tmp/ugc_moderation_trace.jsonl"))


def _load() -> list[dict]:
    if not TRACE.exists():
        return []
    rows = []
    for line in TRACE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def _by_case(rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        grouped[r.get("case_id", "-")].append(r)
    return grouped


def _bar(frac: float, width: int = 40) -> str:
    filled = int(round(frac * width))
    return "█" * filled + "·" * (width - filled)


def _render_case(case_id: str, rows: list[dict]) -> None:
    print(f"\n{'='*100}\nCase: {case_id}   ({len(rows)} events)\n{'='*100}")

    # Extract spans (start + matching end)
    starts: dict[str, dict] = {}
    spans: list[dict] = []
    events: list[dict] = []
    for r in rows:
        if r.get("phase") == "start":
            starts[r["span_id"]] = r
        elif r.get("phase") == "end":
            s = starts.pop(r["span_id"], None)
            if s:
                spans.append({
                    "span": s["span"],
                    "start_wall": s.get("wall"),
                    "dur_ms": r.get("dur_ms", 0.0),
                    "extra": s.get("extra") or {},
                })
        elif "event" in r:
            events.append(r)

    # Absolute timeline - use first start as origin
    origin = min((s["start_wall"] for s in spans if s["start_wall"]), default=None)
    if origin is None:
        print("(no complete spans)")
        return

    spans.sort(key=lambda s: s["start_wall"])
    pipeline_dur = next((s["dur_ms"] for s in spans if s["span"] == "pipeline"), None)

    total_s = pipeline_dur / 1000 if pipeline_dur else None
    print(f"Total pipeline: {pipeline_dur:.0f} ms ({total_s:.2f} s)" if total_s else "(pipeline span missing)")
    print()
    print(f"  {'t+ms':>6}  {'dur':>8}  {'pct':>5}  timeline{' '*32}  span")
    print(f"  {'-'*6}  {'-'*8}  {'-'*5}  {'-'*40}  {'-'*50}")

    for s in spans:
        offset_ms = (s["start_wall"] - origin) * 1000
        pct = (s["dur_ms"] / pipeline_dur * 100) if pipeline_dur else 0
        start_frac = offset_ms / pipeline_dur if pipeline_dur else 0
        dur_frac = s["dur_ms"] / pipeline_dur if pipeline_dur else 0
        # Build a 40-col timeline bar
        bar_w = 40
        start_col = int(round(start_frac * bar_w))
        fill_col = max(1, int(round(dur_frac * bar_w)))
        end_col = min(bar_w, start_col + fill_col)
        bar = ("·" * start_col) + ("█" * (end_col - start_col)) + ("·" * (bar_w - end_col))
        indent = "  " if s["span"].startswith("tool:") or s["span"] in {"build_session_manager", "build_graph", "graph.invoke_async"} else ""
        dur_str = f"{s['dur_ms']/1000:.2f}s" if s["dur_ms"] >= 1000 else f"{s['dur_ms']:.0f}ms"
        extra_str = ""
        if s["extra"]:
            small = {k: v for k, v in s["extra"].items() if k in {"jurisdiction", "s3_uri", "model", "namespace"}}
            if small:
                extra_str = "  " + json.dumps(small, ensure_ascii=False)
        print(f"  {offset_ms:>6.0f}  {dur_str:>8}  {pct:>4.1f}%  {bar}  {indent}{s['span']}{extra_str}")

    # Events
    print()
    for e in events:
        kind = e.get("event", "?")
        extra = e.get("extra") or {}
        if kind == "node.complete":
            t_ms = extra.get("execution_time_ms")
            t_str = f"{t_ms/1000:.2f}s" if isinstance(t_ms, (int, float)) and t_ms >= 1000 else (f"{t_ms} ms" if t_ms else "—")
            print(f"  • Strands node '{extra.get('node_id')}' execution_time = {t_str}")
        elif kind == "invocation.end":
            print(f"  • final decision={extra.get('decision')}  trace={extra.get('trace')}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--case")
    args = ap.parse_args()

    rows = _load()
    if not rows:
        print(f"No trace rows in {TRACE}. Run an invocation first.")
        return 1

    grouped = _by_case(rows)
    if args.case:
        if args.case not in grouped:
            print(f"Case {args.case} not found. Available: {list(grouped)}")
            return 2
        _render_case(args.case, grouped[args.case])
        return 0

    case_ids = list(grouped)
    if not args.all:
        case_ids = [case_ids[-1]]
    for cid in case_ids:
        _render_case(cid, grouped[cid])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

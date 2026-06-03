"""Lightweight trace instrumentation.

Writes newline-delimited JSON events to $UGC_TRACE_FILE (default:
/tmp/ugc_moderation_trace.jsonl). Each event has a monotonic perf_counter
timestamp so you can compute per-node duration without relying on wall-clock.

Events:
  {"case_id":..., "ts":..., "phase":"start"|"end", "span":"pipeline"|"node:<name>"|"tool:<name>", "dur_ms":..., "extra":{...}}
"""
from __future__ import annotations

import contextlib
import contextvars
import json
import os
import threading
import time
import uuid
from pathlib import Path

_TRACE_FILE = os.environ.get("UGC_TRACE_FILE", "/tmp/ugc_moderation_trace.jsonl")
_lock = threading.Lock()

_current_case: contextvars.ContextVar[str] = contextvars.ContextVar("ugc_case_id", default="-")


def set_case(case_id: str) -> None:
    _current_case.set(case_id)


def current_case() -> str:
    return _current_case.get()


def _write(event: dict) -> None:
    line = json.dumps(event, ensure_ascii=False)
    with _lock:
        try:
            with open(_TRACE_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass


def trace_file() -> Path:
    return Path(_TRACE_FILE)


@contextlib.contextmanager
def span(name: str, case_id: str | None = None, **extra):
    """Record a span start/end with perf_counter duration."""
    cid = case_id or current_case()
    t0 = time.perf_counter()
    wall = time.time()
    event_id = uuid.uuid4().hex[:8]
    _write({"case_id": cid, "span_id": event_id, "span": name,
            "phase": "start", "wall": wall, "extra": extra})
    try:
        yield
    finally:
        dur_ms = (time.perf_counter() - t0) * 1000.0
        _write({"case_id": cid, "span_id": event_id, "span": name,
                "phase": "end", "dur_ms": round(dur_ms, 1), "wall": time.time()})


def log_event(case_id: str | None, kind: str, **extra) -> None:
    cid = case_id or current_case()
    _write({"case_id": cid, "ts": time.time(), "event": kind, "extra": extra})


def reset_trace_file() -> None:
    try:
        Path(_TRACE_FILE).unlink(missing_ok=True)
    except Exception:
        pass

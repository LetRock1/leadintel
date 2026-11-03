"""
Response times of the real-time loop, kept in memory (last 1,000 per kind):
  event_to_score     a tracked website event → the lead is re-scored (POST /api/v1/track)
  trigger_to_action  a trigger (enquiry, abandoned cart ...) → the next-best-action decision is made and carried out
Shown on the dashboard's Learning loop page (median and 95th percentile).
"""

import threading
import time
from collections import deque

_lock = threading.Lock()
_data = {}


def record(kind, ms):
    with _lock:
        _data.setdefault(kind, deque(maxlen=1000)).append(float(ms))


class timer:
    """with perf.timer('event_to_score'): ..."""

    def __init__(self, kind):
        self.kind = kind

    def __enter__(self):
        self.t = time.perf_counter()
        return self

    def __exit__(self, *exc):
        record(self.kind, (time.perf_counter() - self.t) * 1000)
        return False


def _quantile(ordered: list[float], q: float) -> float:
    """The q-quantile of an already sorted list (nearest rank)."""
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def summary():
    out = {}
    with _lock:
        items = {k: list(v) for k, v in _data.items()}
    for k, v in items.items():
        if not v:
            continue
        s = sorted(v)
        out[k] = {
            "count": len(s),
            "median_ms": round(_quantile(s, 0.5), 1),
            "p95_ms": round(_quantile(s, 0.95), 1),
            "max_ms": round(s[-1], 1),
        }
    return out

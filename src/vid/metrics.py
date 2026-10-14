"""Latency and traffic counters, measured from phase A on (plan, Sec 8 risks)."""

from __future__ import annotations

import statistics
import threading
import time
from collections import deque
from dataclasses import dataclass


@dataclass
class Sample:
    adapter: str
    status: int
    stream: bool
    overhead_ms: float   # time Vid spent before the call left for the model
    ttfb_ms: float       # model's time to first byte, as Vid saw it
    total_ms: float


class Metrics:
    def __init__(self, keep: int = 1000):
        self.started = time.time()
        self._lock = threading.Lock()
        self._samples: deque[Sample] = deque(maxlen=keep)
        self.requests = 0
        self.errors = 0

    def record(self, s: Sample) -> None:
        with self._lock:
            self._samples.append(s)
            self.requests += 1
            if s.status >= 500:
                self.errors += 1

    def summary(self) -> dict:
        with self._lock:
            samples = list(self._samples)
        def pct(values: list[float], q: float) -> float | None:
            if not values:
                return None
            values = sorted(values)
            return round(values[min(len(values) - 1, int(q * len(values)))], 2)
        over = [s.overhead_ms for s in samples]
        return {
            "uptime_s": round(time.time() - self.started, 1),
            "requests": self.requests,
            "upstream_errors": self.errors,
            "overhead_ms": {
                "median": round(statistics.median(over), 2) if over else None,
                "p95": pct(over, 0.95),
                "max": round(max(over), 2) if over else None,
            },
            "streaming_share": round(sum(s.stream for s in samples) / len(samples), 3) if samples else None,
        }

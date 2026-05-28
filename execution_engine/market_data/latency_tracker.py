"""execution_engine/market_data/latency_tracker.py
DIX VISION v42.2 — Market Data Latency Tracker

Measures and tracks end-to-end latency between exchange-side event
timestamps and local processing timestamps. Maintains rolling
percentile statistics (p50, p95, p99) with a bounded window.

Thread-safe. Pure stats — no IO, no clock reads in core logic.
Callers supply ts_ns values explicitly (INV-15).
"""

from __future__ import annotations

import math
import threading
from collections import deque
from dataclasses import dataclass
from typing import Any


_DEFAULT_WINDOW = 1000


@dataclass(frozen=True, slots=True)
class LatencySample:
    """A single latency observation."""
    source: str          # exchange id or adapter id
    symbol: str
    latency_ns: int      # processing_ts_ns - exchange_ts_ns
    ts_ns: int           # when this sample was recorded


@dataclass(frozen=True, slots=True)
class LatencyStats:
    """Rolling latency statistics snapshot."""
    source: str
    sample_count: int
    min_ns: int
    max_ns: int
    mean_ns: float
    p50_ns: int
    p95_ns: int
    p99_ns: int
    ts_ns: int


def _percentile(sorted_vals: list[int], pct: float) -> int:
    if not sorted_vals:
        return 0
    idx = max(0, int(math.ceil(pct / 100.0 * len(sorted_vals))) - 1)
    return sorted_vals[idx]


class LatencyTracker:
    """
    Tracks market-data latency with a bounded rolling window.

    Thread-safe. Callers record observations via record(); stats()
    returns a frozen LatencyStats snapshot.
    """

    def __init__(self, window: int = _DEFAULT_WINDOW) -> None:
        self._window = window
        self._lock = threading.Lock()
        # source → deque of latency_ns samples
        self._buckets: dict[str, deque[int]] = {}
        self._all: deque[LatencySample] = deque(maxlen=window * 10)

    def record(
        self,
        source: str,
        symbol: str,
        exchange_ts_ns: int,
        processing_ts_ns: int,
        ts_ns: int,
    ) -> LatencySample:
        """Record one latency observation."""
        latency_ns = max(0, processing_ts_ns - exchange_ts_ns)
        sample = LatencySample(
            source=source,
            symbol=symbol,
            latency_ns=latency_ns,
            ts_ns=ts_ns,
        )
        with self._lock:
            if source not in self._buckets:
                self._buckets[source] = deque(maxlen=self._window)
            self._buckets[source].append(latency_ns)
            self._all.append(sample)
        return sample

    def stats(self, source: str, ts_ns: int) -> LatencyStats:
        """Return rolling stats for a specific source."""
        with self._lock:
            samples = list(self._buckets.get(source, []))

        if not samples:
            return LatencyStats(
                source=source,
                sample_count=0,
                min_ns=0,
                max_ns=0,
                mean_ns=0.0,
                p50_ns=0,
                p95_ns=0,
                p99_ns=0,
                ts_ns=ts_ns,
            )

        sorted_s = sorted(samples)
        mean = sum(sorted_s) / len(sorted_s)
        return LatencyStats(
            source=source,
            sample_count=len(sorted_s),
            min_ns=sorted_s[0],
            max_ns=sorted_s[-1],
            mean_ns=mean,
            p50_ns=_percentile(sorted_s, 50),
            p95_ns=_percentile(sorted_s, 95),
            p99_ns=_percentile(sorted_s, 99),
            ts_ns=ts_ns,
        )

    def all_sources(self) -> list[str]:
        with self._lock:
            return list(self._buckets.keys())

    def snapshot(self, ts_ns: int) -> dict[str, Any]:
        sources = self.all_sources()
        return {
            "sources": {s: self.stats(s, ts_ns).__dict__ for s in sources},
            "total_samples": sum(len(v) for v in self._buckets.values()),
        }


__all__ = ["LatencySample", "LatencyStats", "LatencyTracker"]

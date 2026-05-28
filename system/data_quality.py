"""system.data_quality — real-time data quality monitor.

Tracks staleness, anomaly flags, and missing-value rates for named
data streams (market feeds, on-chain oracles, news streams). Surfaces
quality degradation so the health monitor can react before stale data
reaches downstream strategy or risk logic.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any


@dataclass
class StreamQuality:
    stream_id: str
    last_update_ns: int = 0
    stale: bool = False
    anomaly_count: int = 0
    missing_count: int = 0
    total_updates: int = 0


class DataQualityMonitor:
    """Thread-safe data quality tracker for named streams."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._streams: dict[str, StreamQuality] = {}

    def update(
        self,
        stream_id: str,
        ts_ns: int,
        *,
        missing: bool = False,
        anomaly: bool = False,
    ) -> None:
        with self._lock:
            q = self._streams.setdefault(stream_id, StreamQuality(stream_id=stream_id))
            q.last_update_ns = ts_ns
            q.total_updates += 1
            q.stale = False
            if missing:
                q.missing_count += 1
            if anomaly:
                q.anomaly_count += 1

    def mark_stale(self, stream_id: str) -> None:
        with self._lock:
            q = self._streams.setdefault(stream_id, StreamQuality(stream_id=stream_id))
            q.stale = True

    def is_healthy(self, stream_id: str) -> bool:
        with self._lock:
            q = self._streams.get(stream_id)
            return True if q is None else not q.stale

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                sid: {
                    "stale": q.stale,
                    "anomalies": q.anomaly_count,
                    "missing": q.missing_count,
                    "updates": q.total_updates,
                }
                for sid, q in self._streams.items()
            }


_monitor: DataQualityMonitor | None = None
_lock = threading.Lock()


def get_data_quality_monitor() -> DataQualityMonitor:
    global _monitor
    if _monitor is None:
        with _lock:
            if _monitor is None:
                _monitor = DataQualityMonitor()
    return _monitor

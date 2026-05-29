"""state.memory.stores.runtime_events — RuntimeEventMemoryStore.

Records runtime health events: component failures, recovery sequences,
latency spikes, memory pressure, topology anomalies.

DYON uses this store to detect recurring failure patterns and build
autonomous repair plans based on historical recovery evidence.
"""

from __future__ import annotations

import logging
import threading
from collections import deque, defaultdict
from types import MappingProxyType
from typing import Any

from state.memory.contracts import MemoryKind, MemoryRecord

_logger   = logging.getLogger(__name__)
_MAX_SIZE = 3_000


class RuntimeEventMemoryStore:
    """Append-only ring-buffer of runtime health and diagnostic events."""

    def __init__(self, max_size: int = _MAX_SIZE) -> None:
        self._max_size = max_size
        self._lock     = threading.Lock()
        self._records: deque[MemoryRecord] = deque(maxlen=max_size)
        # component → list of (ts_ns, event_type)
        self._by_component: dict[str, list[tuple[int, str]]] = defaultdict(list)
        self._severity_counts: dict[str, int] = defaultdict(int)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record_health_event(
        self,
        *,
        record_id:  str,
        component:  str,
        event_type: str,
        severity:   str,
        ts_ns:      int,
        detail:     str,
        source:     str = "system_monitor",
        tags:       frozenset[str] = frozenset(),
    ) -> MemoryRecord:
        rec = MemoryRecord(
            record_id  = record_id,
            kind       = MemoryKind.RUNTIME,
            ts_ns      = ts_ns,
            source     = source,
            summary    = f"HEALTH [{severity}] {component}/{event_type}: {detail}",
            body       = MappingProxyType({
                "component":  component,
                "event_type": event_type,
                "severity":   severity,
                "detail":     detail,
            }),
            tags       = tags | frozenset([component, event_type.lower(), severity.lower(), "health"]),
            confidence = 1.0 if severity in ("CRITICAL", "ERROR") else 0.5,
        )
        with self._lock:
            self._records.append(rec)
            self._by_component[component].append((ts_ns, event_type))
            self._severity_counts[severity] += 1
        return rec

    def record_failure(
        self,
        *,
        record_id:  str,
        component:  str,
        ts_ns:      int,
        error:      str,
        source:     str = "system_monitor",
        tags:       frozenset[str] = frozenset(),
    ) -> MemoryRecord:
        return self.record_health_event(
            record_id  = record_id,
            component  = component,
            event_type = "FAILURE",
            severity   = "CRITICAL",
            ts_ns      = ts_ns,
            detail     = error,
            source     = source,
            tags       = tags | frozenset(["failure"]),
        )

    def record_recovery(
        self,
        *,
        record_id:  str,
        component:  str,
        ts_ns:      int,
        strategy:   str,
        source:     str = "system_monitor",
        tags:       frozenset[str] = frozenset(),
    ) -> MemoryRecord:
        return self.record_health_event(
            record_id  = record_id,
            component  = component,
            event_type = "RECOVERY",
            severity   = "INFO",
            ts_ns      = ts_ns,
            detail     = f"recovered via {strategy}",
            source     = source,
            tags       = tags | frozenset(["recovery"]),
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def failure_frequency(self, component: str, window_ns: int = 3_600_000_000_000) -> int:
        """Count failures for component within the last window_ns nanoseconds."""
        cutoff = None
        with self._lock:
            events = list(self._by_component.get(component, []))
        if not events:
            return 0
        latest = max(ts for ts, _ in events)
        cutoff = latest - window_ns
        return sum(1 for ts, et in events if et == "FAILURE" and ts >= cutoff)

    def recurring_failures(self, min_count: int = 3) -> list[dict]:
        """Return components with >= min_count failures in last hour."""
        with self._lock:
            components = list(self._by_component.keys())
        return [
            {"component": c, "failure_count": self.failure_frequency(c)}
            for c in components
            if self.failure_frequency(c) >= min_count
        ]

    def recent(self, limit: int = 20) -> list[MemoryRecord]:
        with self._lock:
            recs = list(self._records)
        recs.sort(key=lambda r: r.ts_ns, reverse=True)
        return recs[:limit]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "active":           True,
                "size":             len(self._records),
                "max_size":         self._max_size,
                "components":       len(self._by_component),
                "severity_counts":  dict(self._severity_counts),
                "recurring_failures": self.recurring_failures(min_count=3),
            }


_singleton: RuntimeEventMemoryStore | None = None
_lock = threading.Lock()


def get_runtime_event_memory_store() -> RuntimeEventMemoryStore:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = RuntimeEventMemoryStore()
    return _singleton


__all__ = ["RuntimeEventMemoryStore", "get_runtime_event_memory_store"]

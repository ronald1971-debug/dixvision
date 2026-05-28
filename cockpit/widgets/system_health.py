"""Cockpit widget — system health panel.

Aggregates engine liveness, bus lane backpressure, and latency
percentiles for the operator dashboard. Read-only. B1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["HealthRow", "SystemHealthState", "SystemHealthWidget"]


@dataclass(frozen=True, slots=True)
class HealthRow:
    component: str
    status: str           # "OK" | "DEGRADED" | "DOWN"
    latency_p99_ms: float
    queue_depth: int
    last_heartbeat_ns: int


@dataclass(frozen=True, slots=True)
class SystemHealthState:
    ts_ns: int
    rows: tuple[HealthRow, ...]
    overall: str          # "OK" | "DEGRADED" | "DOWN"
    stale_components: tuple[str, ...]


_STALE_THRESHOLD_NS = 5_000_000_000  # 5 seconds


class SystemHealthWidget:
    """Read interface for system health rendering."""

    def __init__(self, health_store: Any) -> None:
        self._store = health_store

    def get_state(self, ts_ns: int) -> SystemHealthState:
        components = self._store.all_components()
        rows: list[HealthRow] = []
        stale: list[str] = []
        for c in components:
            age_ns = ts_ns - c.last_heartbeat_ns
            is_stale = age_ns > _STALE_THRESHOLD_NS
            if is_stale:
                stale.append(c.name)
            rows.append(HealthRow(
                component=c.name,
                status="DOWN" if is_stale else c.status,
                latency_p99_ms=c.latency_p99_ms,
                queue_depth=c.queue_depth,
                last_heartbeat_ns=c.last_heartbeat_ns,
            ))
        any_down = any(r.status == "DOWN" for r in rows)
        any_degraded = any(r.status == "DEGRADED" for r in rows)
        overall = "DOWN" if any_down else ("DEGRADED" if any_degraded else "OK")
        return SystemHealthState(
            ts_ns=ts_ns,
            rows=tuple(rows),
            overall=overall,
            stale_components=tuple(stale),
        )

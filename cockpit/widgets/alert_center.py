"""Cockpit widget — alert center.

Aggregates and prioritises active alerts from the hazard lane
and liveness watchdog. Read-only. B1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["AlertEntry", "AlertCenterState", "AlertCenterWidget"]


@dataclass(frozen=True, slots=True)
class AlertEntry:
    alert_id: str
    ts_ns: int
    severity: str       # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO"
    source: str
    message: str
    acknowledged: bool


@dataclass(frozen=True, slots=True)
class AlertCenterState:
    ts_ns: int
    alerts: tuple[AlertEntry, ...]
    unacknowledged_count: int
    critical_count: int


_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}


class AlertCenterWidget:
    """Read/acknowledge interface for alert center panel."""

    def __init__(self, alert_store: Any) -> None:
        self._store = alert_store

    def get_state(self, ts_ns: int, limit: int = 50) -> AlertCenterState:
        raw = self._store.active(limit=limit)
        alerts = tuple(
            sorted(raw, key=lambda a: _SEVERITY_ORDER.get(a.severity, 99))
        )
        unack = sum(1 for a in alerts if not a.acknowledged)
        critical = sum(1 for a in alerts if a.severity == "CRITICAL")
        return AlertCenterState(
            ts_ns=ts_ns,
            alerts=alerts,
            unacknowledged_count=unack,
            critical_count=critical,
        )

    def acknowledge(self, alert_id: str, operator_id: str, ts_ns: int) -> bool:
        return self._store.acknowledge(alert_id=alert_id,
                                       operator_id=operator_id, ts_ns=ts_ns)

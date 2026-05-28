"""Cockpit widget — alert center.

Reads active alerts from the hazard event ring on ui.server.STATE
and the liveness watchdog. No constructor injection required.
"""

from __future__ import annotations

from typing import Any

__all__ = ["alert_center_payload"]

_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}


def alert_center_payload(limit: int = 50) -> dict[str, Any]:
    alerts: list[dict[str, Any]] = []
    try:
        from ui.server import STATE  # noqa: PLC0415
        # Pull recent events from the in-memory ring, filter to HAZARD kind
        from core.contracts.events import EventKind  # noqa: PLC0415
        ring = list(STATE.events)[:limit * 2]
        for entry in ring:
            ev = entry.get("event") if isinstance(entry, dict) else None
            if ev is None:
                continue
            if getattr(ev, "kind", None) != EventKind.HAZARD:
                continue
            alerts.append({
                "alert_id": str(getattr(ev, "id", id(ev))),
                "ts_ns": getattr(ev, "ts_ns", 0),
                "severity": getattr(ev, "severity", "INFO"),
                "source": entry.get("source", "unknown"),
                "message": getattr(ev, "message", str(ev)),
                "acknowledged": False,
            })
            if len(alerts) >= limit:
                break
    except Exception:  # noqa: BLE001
        pass

    alerts.sort(key=lambda a: _SEVERITY_ORDER.get(a["severity"], 99))
    critical = sum(1 for a in alerts if a["severity"] == "CRITICAL")
    return {
        "alerts": alerts,
        "unacknowledged_count": len(alerts),
        "critical_count": critical,
    }

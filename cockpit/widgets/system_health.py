"""Cockpit widget — system health panel.

Reads engine liveness from system_monitor and the system kernel state projection.
No constructor injection required.
"""

from __future__ import annotations

from typing import Any

from system_monitor.dead_man import get_dead_man
from system_monitor.latency_guard import get_latency_guard

__all__ = ["system_health_payload"]

_STALE_NS = 5_000_000_000  # 5 seconds


def system_health_payload() -> dict[str, Any]:
    dead_man = get_dead_man()
    latency = get_latency_guard()

    components = []
    try:
        from ui.server import STATE  # noqa: PLC0415
        snap = STATE.system_kernel.snapshot
        for svc in snap.services:
            components.append({
                "name": svc.name,
                "status": svc.phase.value if hasattr(svc, "phase") else "UNKNOWN",
                "latency_p99_ms": latency.p99_ms(svc.name),
                "last_heartbeat_ns": getattr(svc, "last_heartbeat_ns", 0),
            })
    except Exception:  # noqa: BLE001
        pass

    any_down = any(c["status"] in ("ERROR", "OFFLINE", "DOWN") for c in components)
    any_degraded = any(c["status"] == "DEGRADED" for c in components)
    overall = "DOWN" if any_down else ("DEGRADED" if any_degraded else "OK")

    return {
        "overall": overall,
        "components": components,
        "dead_man_armed": dead_man.is_armed(),
        "latency_guard_triggered": latency.is_triggered(),
    }

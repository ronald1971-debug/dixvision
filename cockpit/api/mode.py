"""Cockpit API — /mode payload builder.

Operating mode here refers to the system health mode (NORMAL / DEGRADED /
SAFE_MODE / EMERGENCY_HALT) managed by governance.mode_manager, distinct
from the autonomy mode in autonomy.py.
Called by ui/cockpit_routes.py.
"""

from __future__ import annotations

from typing import Any

__all__ = ["mode_payload"]


def mode_payload() -> dict[str, Any]:
    try:
        from governance.mode_manager import get_mode_manager  # noqa: PLC0415
        mm = get_mode_manager()
        return {
            "current_mode": mm.current_mode().value,
            "since_ns": mm.since_ns(),
            "transition_count": mm.transition_count(),
        }
    except ImportError:
        # Fallback: read from the system kernel state projection
        try:
            from ui.server import STATE  # noqa: PLC0415
            mode = STATE.system_kernel.snapshot.mode
            return {"current_mode": mode.value, "since_ns": 0, "transition_count": 0}
        except Exception:  # noqa: BLE001
            return {"current_mode": "UNKNOWN", "since_ns": 0, "transition_count": 0}

"""Cockpit widget — plugin manager panel.

Reads plugin state from STATE.plugin_registry and the governance activation gate.
No constructor injection required.
"""

from __future__ import annotations

from typing import Any

__all__ = ["plugin_list_payload", "toggle_plugin", "request_reload"]


def plugin_list_payload() -> dict[str, Any]:
    try:
        from ui.server import STATE  # noqa: PLC0415
        registry = STATE.plugin_registry
        plugins = []
        for p in registry.all():
            plugins.append({
                "plugin_id": getattr(p, "id", str(p)),
                "version": getattr(p, "version", ""),
                "state": getattr(p, "state", "UNKNOWN"),
                "last_reload_ns": getattr(p, "last_reload_ns", 0),
            })
        return {"plugins": plugins, "count": len(plugins)}
    except Exception as exc:  # noqa: BLE001
        return {"plugins": [], "count": 0, "error": str(exc)}


def toggle_plugin(plugin_id: str, enable: bool, operator_id: str) -> dict[str, Any]:
    try:
        from ui.server import STATE  # noqa: PLC0415
        STATE.plugin_registry.set_active(plugin_id, active=enable)
        return {"accepted": True, "plugin_id": plugin_id, "enabled": enable}
    except Exception as exc:  # noqa: BLE001
        return {"accepted": False, "reason": str(exc)}


def request_reload(plugin_id: str) -> dict[str, Any]:
    try:
        from governance_engine.plugin_lifecycle.hot_reload_signal import get_reload_signal  # noqa: PLC0415
        from system.time_source import wall_ns  # noqa: PLC0415
        get_reload_signal().enqueue(plugin_id=plugin_id, ts_ns=wall_ns())
        return {"accepted": True, "queued": True}
    except Exception as exc:  # noqa: BLE001
        return {"accepted": False, "reason": str(exc)}

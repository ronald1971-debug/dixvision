"""Cockpit widget — plugin manager panel.

UI data model for listing, enabling, disabling, and hot-reloading plugins.
B1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["PluginEntry", "PluginManagerWidget"]


@dataclass(frozen=True, slots=True)
class PluginEntry:
    plugin_id: str
    version: str
    state: str           # "ACTIVE" | "INACTIVE" | "ERROR" | "LOADING"
    activation_gate: str # "ALLOWED" | "DENIED" | "REQUIRES_OPERATOR"
    last_reload_ns: int


class PluginManagerWidget:
    """Read/write interface for the plugin manager UI panel."""

    def __init__(self, plugin_registry: Any, activation_gate: Any,
                 reload_signal: Any) -> None:
        self._registry = plugin_registry
        self._gate = activation_gate
        self._reload = reload_signal

    def list_plugins(self) -> tuple[PluginEntry, ...]:
        return tuple(
            PluginEntry(
                plugin_id=p.id,
                version=p.version,
                state=p.state,
                activation_gate=self._gate.check(p.id).name,
                last_reload_ns=p.last_reload_ns,
            )
            for p in self._registry.all()
        )

    def toggle(self, plugin_id: str, enable: bool, operator_id: str,
               ts_ns: int) -> dict[str, Any]:
        gate_result = self._gate.check(plugin_id)
        if gate_result.name == "DENIED":
            return {"accepted": False, "reason": "Plugin activation denied by gate"}
        if gate_result.name == "REQUIRES_OPERATOR" and not operator_id:
            return {"accepted": False, "reason": "Operator approval required"}
        self._registry.set_active(plugin_id, active=enable, ts_ns=ts_ns)
        return {"accepted": True, "reason": ""}

    def request_hot_reload(self, plugin_id: str, ts_ns: int) -> dict[str, Any]:
        self._reload.enqueue(plugin_id=plugin_id, ts_ns=ts_ns)
        return {"accepted": True, "queued": True}

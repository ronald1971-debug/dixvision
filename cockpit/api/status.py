"""Cockpit API — /status endpoint.

Returns system health summary: engine states, active strategies,
bus lane status, last event timestamps. B1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["SystemStatus", "StatusProvider"]


@dataclass(frozen=True, slots=True)
class EngineStatus:
    name: str
    state: str       # "RUNNING" | "PAUSED" | "ERROR" | "OFFLINE"
    last_event_ns: int


@dataclass(frozen=True, slots=True)
class SystemStatus:
    ts_ns: int
    overall: str     # "HEALTHY" | "DEGRADED" | "HALTED"
    engines: tuple[EngineStatus, ...]
    active_strategies: tuple[str, ...]
    kill_switch_active: bool
    safe_mode_active: bool


class StatusProvider:
    """Assembles SystemStatus from injected state readers."""

    def __init__(
        self,
        engine_state_reader: Any,
        strategy_registry: Any,
        kill_switch: Any,
    ) -> None:
        self._engines = engine_state_reader
        self._strategies = strategy_registry
        self._kill_switch = kill_switch

    def get_status(self, ts_ns: int) -> SystemStatus:
        engine_statuses = tuple(
            EngineStatus(name=e.name, state=e.state, last_event_ns=e.last_event_ns)
            for e in self._engines.all()
        )
        active = tuple(s.id for s in self._strategies.active())
        ks_active = self._kill_switch.is_active()
        safe_mode = getattr(self._kill_switch, "safe_mode_active", lambda: False)()
        degraded = any(e.state == "ERROR" for e in engine_statuses)
        halted = ks_active or any(e.state == "OFFLINE" for e in engine_statuses)
        overall = "HALTED" if halted else ("DEGRADED" if degraded else "HEALTHY")
        return SystemStatus(
            ts_ns=ts_ns,
            overall=overall,
            engines=engine_statuses,
            active_strategies=active,
            kill_switch_active=ks_active,
            safe_mode_active=safe_mode,
        )

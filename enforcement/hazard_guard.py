"""enforcement.hazard_guard — Hazard Escalation Enforcement.

Build Plan §7 (Phase 6): Enforces that all SYSTEM_HAZARD events follow
the mandatory escalation path and are never silently dropped or bypassed.

Works alongside runtime_guardian.py — the guardian checks heartbeats and
health, while the hazard_guard ensures the hazard pipeline itself is
functioning correctly.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from immutable_core.kill_switch import trigger_kill_switch
from system import time_source


@dataclass(slots=True)
class HazardGuardState:
    last_hazard_ts_ns: int = 0
    hazards_seen: int = 0
    hazards_unresolved: int = 0
    consecutive_critical: int = 0


class HazardGuard:
    """Enforces hazard pipeline integrity at runtime."""

    def __init__(self, *, max_unresolved: int = 50, critical_threshold: int = 3) -> None:
        self._lock = threading.Lock()
        self._state = HazardGuardState()
        self._max_unresolved = max_unresolved
        self._critical_threshold = critical_threshold

    def on_hazard_emitted(self, hazard_type: str, severity: str) -> None:
        """Called when a hazard is emitted — tracks pipeline health."""
        with self._lock:
            self._state.hazards_seen += 1
            self._state.hazards_unresolved += 1
            self._state.last_hazard_ts_ns = time_source.wall_ns()
            if severity == "CRITICAL":
                self._state.consecutive_critical += 1
            else:
                self._state.consecutive_critical = 0

        if self._state.consecutive_critical >= self._critical_threshold:
            trigger_kill_switch(
                f"consecutive_critical_hazards:{self._state.consecutive_critical}",
                "hazard_guard",
            )
        if self._state.hazards_unresolved >= self._max_unresolved:
            trigger_kill_switch(
                f"unresolved_hazard_overflow:{self._state.hazards_unresolved}",
                "hazard_guard",
            )

    def on_hazard_resolved(self) -> None:
        """Called when a hazard is resolved — decrements unresolved count."""
        with self._lock:
            if self._state.hazards_unresolved > 0:
                self._state.hazards_unresolved -= 1

    def get_state(self) -> HazardGuardState:
        with self._lock:
            return HazardGuardState(
                last_hazard_ts_ns=self._state.last_hazard_ts_ns,
                hazards_seen=self._state.hazards_seen,
                hazards_unresolved=self._state.hazards_unresolved,
                consecutive_critical=self._state.consecutive_critical,
            )


_guard: HazardGuard | None = None
_lock = threading.Lock()


def get_hazard_guard() -> HazardGuard:
    global _guard
    if _guard is None:
        with _lock:
            if _guard is None:
                _guard = HazardGuard()
    return _guard

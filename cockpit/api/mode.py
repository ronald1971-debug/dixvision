"""Cockpit API — /mode endpoint.

Reads and sets the system operating mode: LIVE, PAPER, SIM, MAINTENANCE.
Mode transitions are validated and logged. B1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["OperatingMode", "ModeTransitionResult", "ModeController"]

_VALID_MODES = frozenset({"LIVE", "PAPER", "SIM", "MAINTENANCE"})
_VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "LIVE": frozenset({"PAPER", "MAINTENANCE"}),
    "PAPER": frozenset({"LIVE", "SIM", "MAINTENANCE"}),
    "SIM": frozenset({"PAPER", "MAINTENANCE"}),
    "MAINTENANCE": frozenset({"PAPER", "SIM"}),
}


@dataclass(frozen=True, slots=True)
class OperatingMode:
    current: str
    since_ns: int


@dataclass(frozen=True, slots=True)
class ModeTransitionResult:
    ts_ns: int
    from_mode: str
    to_mode: str
    accepted: bool
    rejection_reason: str


class ModeController:
    """Controls and validates operating mode transitions."""

    def __init__(self, mode_store: Any, mode_log: Any) -> None:
        self._store = mode_store
        self._log = mode_log

    def current(self) -> OperatingMode:
        return self._store.get()

    def transition(
        self, ts_ns: int, to_mode: str, operator_id: str
    ) -> ModeTransitionResult:
        current = self._store.get()
        if to_mode not in _VALID_MODES:
            return ModeTransitionResult(
                ts_ns=ts_ns, from_mode=current.current, to_mode=to_mode,
                accepted=False,
                rejection_reason=f"Invalid mode: {to_mode!r}",
            )
        allowed = _VALID_TRANSITIONS.get(current.current, frozenset())
        if to_mode not in allowed:
            return ModeTransitionResult(
                ts_ns=ts_ns, from_mode=current.current, to_mode=to_mode,
                accepted=False,
                rejection_reason=f"Transition {current.current!r} → {to_mode!r} not allowed",
            )
        self._store.set(to_mode, ts_ns=ts_ns)
        self._log.record(
            ts_ns=ts_ns, operator_id=operator_id,
            from_mode=current.current, to_mode=to_mode,
        )
        return ModeTransitionResult(
            ts_ns=ts_ns, from_mode=current.current, to_mode=to_mode,
            accepted=True, rejection_reason="",
        )

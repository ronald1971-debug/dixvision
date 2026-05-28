"""Cockpit audit — operator action log viewer.

Read-only query interface over the operator action ledger.
No side effects. B1. INV-15.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["OperatorAction", "OperatorActionLog"]


@dataclass(frozen=True, slots=True)
class OperatorAction:
    ts_ns: int
    operator_id: str
    action_type: str       # "HALT", "RESUME", "OVERRIDE", "PARAM_CHANGE", "PLUGIN_TOGGLE"
    target: str            # strategy_id, plugin_id, or system component
    payload: dict[str, Any]
    session_id: str


class OperatorActionLog:
    """In-memory store of operator actions with query interface.

    Populated by callers; exposes read-only query methods.
    """

    def __init__(self) -> None:
        self._actions: list[OperatorAction] = []

    def append(self, action: OperatorAction) -> None:
        self._actions.append(action)

    def all(self) -> tuple[OperatorAction, ...]:
        return tuple(self._actions)

    def since(self, ts_ns: int) -> tuple[OperatorAction, ...]:
        return tuple(a for a in self._actions if a.ts_ns >= ts_ns)

    def by_type(self, action_type: str) -> tuple[OperatorAction, ...]:
        return tuple(a for a in self._actions if a.action_type == action_type)

    def by_operator(self, operator_id: str) -> tuple[OperatorAction, ...]:
        return tuple(a for a in self._actions if a.operator_id == operator_id)

    def by_target(self, target: str) -> tuple[OperatorAction, ...]:
        return tuple(a for a in self._actions if a.target == target)

    def count(self) -> int:
        return len(self._actions)

"""Cockpit audit — parameter override log.

Tracks every parameter override applied by operators, including
old/new values and rationale. Read-only query interface. B1. INV-15.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["OverrideEntry", "OverrideLog"]


@dataclass(frozen=True, slots=True)
class OverrideEntry:
    ts_ns: int
    operator_id: str
    strategy_id: str
    parameter: str
    old_value: Any
    new_value: Any
    rationale: str
    session_id: str
    content_hash: str


class OverrideLog:
    """Append-only log of parameter overrides."""

    def __init__(self) -> None:
        self._entries: list[OverrideEntry] = []

    def append(self, entry: OverrideEntry) -> None:
        self._entries.append(entry)

    def all(self) -> tuple[OverrideEntry, ...]:
        return tuple(self._entries)

    def for_strategy(self, strategy_id: str) -> tuple[OverrideEntry, ...]:
        return tuple(e for e in self._entries if e.strategy_id == strategy_id)

    def for_parameter(self, parameter: str) -> tuple[OverrideEntry, ...]:
        return tuple(e for e in self._entries if e.parameter == parameter)

    def since(self, ts_ns: int) -> tuple[OverrideEntry, ...]:
        return tuple(e for e in self._entries if e.ts_ns >= ts_ns)

    def last(self, n: int = 10) -> tuple[OverrideEntry, ...]:
        return tuple(self._entries[-n:])

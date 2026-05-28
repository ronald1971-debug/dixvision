"""Append-only regret event log (state.memory_tensor.regret.regret_log).

RGT-03 — Records structured regret events that pair a realised P&L with a
counterfactual P&L, enabling the learning / evolution tiers to measure
decision quality without accessing live execution state.

Authority constraints:
* B1: No imports from intelligence_engine, execution_engine, governance_engine,
  evolution_engine, learning_engine.
* B27/B28/INV-71: Never constructs SignalEvent, ExecutionEvent, HazardEvent,
  PatchProposal.
* INV-15: Pure functions — no wall-clock reads.
* RUNTIME_SAFE: no clocks, no IO, no PRNG in core value objects.
* Frozen dataclasses: (frozen=True, slots=True).
"""

from __future__ import annotations

import dataclasses
import threading
from enum import StrEnum


__all__ = (
    "RegretKind",
    "RegretEntry",
    "RegretLog",
)


# ---------------------------------------------------------------------------
# Enum
# ---------------------------------------------------------------------------


class RegretKind(StrEnum):
    """Classification of regret events.

    ``MISSED_ENTRY``
        A profitable opportunity was not entered.
    ``EARLY_EXIT``
        A position was closed before its optimal exit point.
    ``LATE_ENTRY``
        An entry was delayed, reducing the captured move.
    ``OVERSIZED``
        Position sizing was too large relative to the optimal size.
    ``UNDERSIZED``
        Position sizing was too small, leaving profit on the table.
    """

    MISSED_ENTRY = "MISSED_ENTRY"
    EARLY_EXIT = "EARLY_EXIT"
    LATE_ENTRY = "LATE_ENTRY"
    OVERSIZED = "OVERSIZED"
    UNDERSIZED = "UNDERSIZED"


# ---------------------------------------------------------------------------
# Value object
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class RegretEntry:
    """Immutable regret event record.

    Fields
    ------
    entry_id:
        Unique identifier for this regret record.
    ts_ns:
        Timestamp in nanoseconds when the regret was recorded
        (caller-supplied — no wall-clock reads per INV-15).
    kind:
        :class:`RegretKind` category of this regret event.
    symbol:
        Instrument symbol the regret relates to.
    realised_pnl:
        Actual P&L achieved on the trade or opportunity window.
    counterfactual_pnl:
        P&L that would have been achieved under the optimal decision.
    regret_pnl:
        ``counterfactual_pnl - realised_pnl``.  Positive values mean
        money was left on the table; negative means the realised outcome
        outperformed the counterfactual (regret of over-caution is
        tracked in the ``UNDERSIZED`` / ``MISSED_ENTRY`` kinds).
        Computed automatically by :class:`RegretLog` from the two P&L
        fields if the caller omits it — or callers may supply it
        directly for auditability.
    detail:
        Optional free-text description of the event for human review.
    """

    entry_id: str
    ts_ns: int
    kind: RegretKind
    symbol: str
    realised_pnl: float
    counterfactual_pnl: float
    regret_pnl: float
    detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.entry_id, str) or not self.entry_id:
            raise ValueError(
                f"RegretEntry.entry_id must be non-empty str, got {self.entry_id!r}"
            )
        if not isinstance(self.ts_ns, int) or isinstance(self.ts_ns, bool):
            raise ValueError(
                f"RegretEntry.ts_ns must be int, got {type(self.ts_ns).__name__}"
            )
        if not isinstance(self.kind, RegretKind):
            raise ValueError(
                f"RegretEntry.kind must be RegretKind, got {type(self.kind).__name__}"
            )
        if not isinstance(self.symbol, str) or not self.symbol:
            raise ValueError(
                f"RegretEntry.symbol must be non-empty str, got {self.symbol!r}"
            )
        if not isinstance(self.realised_pnl, float):
            raise ValueError(
                f"RegretEntry.realised_pnl must be float, got {type(self.realised_pnl).__name__}"
            )
        if not isinstance(self.counterfactual_pnl, float):
            raise ValueError(
                "RegretEntry.counterfactual_pnl must be float, "
                f"got {type(self.counterfactual_pnl).__name__}"
            )
        if not isinstance(self.regret_pnl, float):
            raise ValueError(
                f"RegretEntry.regret_pnl must be float, got {type(self.regret_pnl).__name__}"
            )
        if not isinstance(self.detail, str):
            raise ValueError(
                f"RegretEntry.detail must be str, got {type(self.detail).__name__}"
            )


# ---------------------------------------------------------------------------
# Log
# ---------------------------------------------------------------------------


class RegretLog:
    """Thread-safe append-only log of :class:`RegretEntry` records.

    All mutation is serialized through a :class:`threading.Lock`.
    Read methods snapshot the list under the lock and release it
    immediately, keeping lock hold-time minimal.
    """

    __slots__ = ("_lock", "_entries")

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._entries: list[RegretEntry] = []

    def append(self, entry: RegretEntry) -> None:
        """Append *entry* to the log.

        Raises
        ------
        TypeError:
            If *entry* is not a :class:`RegretEntry`.
        """
        if not isinstance(entry, RegretEntry):
            raise TypeError(
                f"RegretLog.append: expected RegretEntry, got {type(entry).__name__}"
            )
        with self._lock:
            self._entries.append(entry)

    def all(self) -> tuple[RegretEntry, ...]:
        """Return all entries in insertion order."""
        with self._lock:
            return tuple(self._entries)

    def total_regret_pnl(self) -> float:
        """Return the sum of ``regret_pnl`` across all entries.

        Uses :func:`math.fsum` for numerically stable accumulation.
        Returns ``0.0`` for an empty log.
        """
        import math

        with self._lock:
            values = [e.regret_pnl for e in self._entries]
        return math.fsum(values) if values else 0.0

    def by_kind(self, kind: RegretKind) -> tuple[RegretEntry, ...]:
        """Return all entries matching *kind* in insertion order.

        Raises
        ------
        ValueError:
            If *kind* is not a :class:`RegretKind`.
        """
        if not isinstance(kind, RegretKind):
            raise ValueError(
                f"RegretLog.by_kind: kind must be RegretKind, got {type(kind).__name__}"
            )
        with self._lock:
            return tuple(e for e in self._entries if e.kind == kind)

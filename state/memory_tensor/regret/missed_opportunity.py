"""Missed opportunity tracker (state.memory_tensor.regret.missed_opportunity).

RGT-01 — Records market opportunities that were available but not taken,
capturing the signal direction, expected P&L, and the reason the system
declined to act.  Used by learning / evolution tiers to improve coverage.

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


__all__ = (
    "MissedOpportunity",
    "MissedOpportunityLog",
)

# Allowed direction values.
_VALID_DIRECTIONS: frozenset[str] = frozenset({"BUY", "SELL"})


# ---------------------------------------------------------------------------
# Value object
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class MissedOpportunity:
    """Immutable record of one missed market opportunity.

    Fields
    ------
    opportunity_id:
        Unique identifier for this opportunity record.
    ts_ns:
        Timestamp in nanoseconds when the opportunity was identified
        (caller-supplied — no wall-clock reads per INV-15).
    symbol:
        Instrument symbol for the opportunity.
    direction:
        Trade direction — ``"BUY"`` or ``"SELL"``.
    expected_pnl:
        Model-estimated P&L had the trade been taken (in base currency
        units; can be negative if a short was skipped at the wrong time).
    reason_skipped:
        Human-readable / symbolic reason the system decided not to act
        (e.g. ``"BELOW_CONFIDENCE_THRESHOLD"``, ``"RISK_LIMIT_BREACH"``).
    meta:
        Ordered ``(key: str, value: str)`` pairs carrying arbitrary
        supplementary context.
    """

    opportunity_id: str
    ts_ns: int
    symbol: str
    direction: str
    expected_pnl: float
    reason_skipped: str
    meta: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.opportunity_id, str) or not self.opportunity_id:
            raise ValueError(
                "MissedOpportunity.opportunity_id must be non-empty str, "
                f"got {self.opportunity_id!r}"
            )
        if not isinstance(self.ts_ns, int) or isinstance(self.ts_ns, bool):
            raise ValueError(
                f"MissedOpportunity.ts_ns must be int, got {type(self.ts_ns).__name__}"
            )
        if not isinstance(self.symbol, str) or not self.symbol:
            raise ValueError(
                f"MissedOpportunity.symbol must be non-empty str, got {self.symbol!r}"
            )
        if self.direction not in _VALID_DIRECTIONS:
            raise ValueError(
                f"MissedOpportunity.direction must be one of {sorted(_VALID_DIRECTIONS)!r}, "
                f"got {self.direction!r}"
            )
        if not isinstance(self.expected_pnl, float):
            raise ValueError(
                "MissedOpportunity.expected_pnl must be float, "
                f"got {type(self.expected_pnl).__name__}"
            )
        if not isinstance(self.reason_skipped, str):
            raise ValueError(
                "MissedOpportunity.reason_skipped must be str, "
                f"got {type(self.reason_skipped).__name__}"
            )
        if not isinstance(self.meta, tuple):
            raise ValueError(
                f"MissedOpportunity.meta must be tuple, got {type(self.meta).__name__}"
            )
        for i, pair in enumerate(self.meta):
            if (
                not isinstance(pair, tuple)
                or len(pair) != 2
                or not isinstance(pair[0], str)
                or not isinstance(pair[1], str)
            ):
                raise ValueError(
                    f"MissedOpportunity.meta[{i}] must be (str, str) tuple, got {pair!r}"
                )


# ---------------------------------------------------------------------------
# Log
# ---------------------------------------------------------------------------


class MissedOpportunityLog:
    """Thread-safe append-only log of :class:`MissedOpportunity` records."""

    __slots__ = ("_lock", "_entries")

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._entries: list[MissedOpportunity] = []

    def record(self, opp: MissedOpportunity) -> None:
        """Append *opp* to the log.

        Raises
        ------
        TypeError:
            If *opp* is not a :class:`MissedOpportunity`.
        """
        if not isinstance(opp, MissedOpportunity):
            raise TypeError(
                f"MissedOpportunityLog.record: expected MissedOpportunity, "
                f"got {type(opp).__name__}"
            )
        with self._lock:
            self._entries.append(opp)

    def all(self) -> tuple[MissedOpportunity, ...]:
        """Return all entries in insertion order."""
        with self._lock:
            return tuple(self._entries)

    def by_symbol(self, symbol: str) -> tuple[MissedOpportunity, ...]:
        """Return all entries matching *symbol* in insertion order."""
        if not isinstance(symbol, str) or not symbol:
            raise ValueError(
                "MissedOpportunityLog.by_symbol: symbol must be non-empty str"
            )
        with self._lock:
            return tuple(e for e in self._entries if e.symbol == symbol)

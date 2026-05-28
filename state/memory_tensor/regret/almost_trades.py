"""Near-miss trade tracking (state.memory_tensor.regret.almost_trades).

RGT-02 — Records trades that came close to executing but fell short of
the confidence threshold.  The ``miss_delta`` field quantifies how far
below the threshold confidence was, enabling threshold-calibration
analytics.

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
    "AlmostTrade",
    "AlmostTradeLog",
)


# ---------------------------------------------------------------------------
# Value object
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class AlmostTrade:
    """Immutable record of one near-miss trade event.

    Fields
    ------
    trade_id:
        Unique identifier for this near-miss record.
    ts_ns:
        Timestamp in nanoseconds when the near-miss was captured
        (caller-supplied — no wall-clock reads per INV-15).
    symbol:
        Instrument symbol.
    side:
        Intended trade side (e.g. ``"BUY"`` or ``"SELL"``).
    confidence:
        Model confidence score at the time of evaluation.
    threshold_at_time:
        The confidence threshold that was in effect at ``ts_ns``.
    miss_delta:
        ``threshold_at_time - confidence``: positive means the trade was
        below the threshold; a value ≤ 0 indicates the trade should have
        executed (caller should not record those as near-misses).
    """

    trade_id: str
    ts_ns: int
    symbol: str
    side: str
    confidence: float
    threshold_at_time: float
    miss_delta: float

    def __post_init__(self) -> None:
        if not isinstance(self.trade_id, str) or not self.trade_id:
            raise ValueError(
                f"AlmostTrade.trade_id must be non-empty str, got {self.trade_id!r}"
            )
        if not isinstance(self.ts_ns, int) or isinstance(self.ts_ns, bool):
            raise ValueError(
                f"AlmostTrade.ts_ns must be int, got {type(self.ts_ns).__name__}"
            )
        if not isinstance(self.symbol, str) or not self.symbol:
            raise ValueError(
                f"AlmostTrade.symbol must be non-empty str, got {self.symbol!r}"
            )
        if not isinstance(self.side, str) or not self.side:
            raise ValueError(
                f"AlmostTrade.side must be non-empty str, got {self.side!r}"
            )
        if not isinstance(self.confidence, float):
            raise ValueError(
                f"AlmostTrade.confidence must be float, got {type(self.confidence).__name__}"
            )
        if not isinstance(self.threshold_at_time, float):
            raise ValueError(
                "AlmostTrade.threshold_at_time must be float, "
                f"got {type(self.threshold_at_time).__name__}"
            )
        if not isinstance(self.miss_delta, float):
            raise ValueError(
                f"AlmostTrade.miss_delta must be float, got {type(self.miss_delta).__name__}"
            )


# ---------------------------------------------------------------------------
# Log
# ---------------------------------------------------------------------------


class AlmostTradeLog:
    """Thread-safe append-only log of :class:`AlmostTrade` records."""

    __slots__ = ("_lock", "_entries")

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._entries: list[AlmostTrade] = []

    def record(self, trade: AlmostTrade) -> None:
        """Append *trade* to the log.

        Raises
        ------
        TypeError:
            If *trade* is not an :class:`AlmostTrade`.
        """
        if not isinstance(trade, AlmostTrade):
            raise TypeError(
                f"AlmostTradeLog.record: expected AlmostTrade, got {type(trade).__name__}"
            )
        with self._lock:
            self._entries.append(trade)

    def all(self) -> tuple[AlmostTrade, ...]:
        """Return all entries in insertion order."""
        with self._lock:
            return tuple(self._entries)

    def above_confidence(self, min_confidence: float) -> tuple[AlmostTrade, ...]:
        """Return entries whose ``confidence >= min_confidence`` in insertion order.

        Parameters
        ----------
        min_confidence:
            Inclusive lower bound on the ``confidence`` field.

        Raises
        ------
        ValueError:
            If *min_confidence* is not a :class:`float`.
        """
        if not isinstance(min_confidence, float):
            raise ValueError(
                "AlmostTradeLog.above_confidence: min_confidence must be float, "
                f"got {type(min_confidence).__name__}"
            )
        with self._lock:
            return tuple(e for e in self._entries if e.confidence >= min_confidence)

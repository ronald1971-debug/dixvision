"""execution_engine.pipeline_coordinator — Async Execution Pipeline Coordinator.

Runs as a background service coordinating execution requests from the
runtime kernel tick loop. Manages:

1. Intent queue (priority-ordered execution requests)
2. Concurrent dispatch (multi-venue parallel execution)
3. Fill aggregation (combine partial fills across venues)
4. Position tracking (net position per symbol)
5. PnL attribution (per-strategy, per-venue breakdown)

Architecture alignment (manifest invariants):
- INV-15 (Replay Determinism): All timestamps are caller-supplied via
  ts_ns. No raw time.time(), datetime.now(), or time.time_ns() calls.
- INV-56 (Triad Lock): The coordinator does NOT call adapters directly.
  It queues intents for the ExecutionOrchestrator which enforces
  governance gates.
- INV-68 (ExecutionIntent Immutability): Queue items are frozen once
  submitted; no mutation between submission and processing.
- BeliefState integration: Position tracking correlates with the
  current regime for offline calibration.
- SignalTrust: Each fill records the trust class of the originating
  signal for governance audit.

__capability_tier__ = 4  # GOVERNED_PAPER_EXECUTION
__forbidden_tiers__ = ()
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols (B1 — no cross-engine imports)
# ---------------------------------------------------------------------------


class LedgerWriterProtocol(Protocol):
    """Authority ledger writer (append-only, hash-chained)."""

    def append(self, *, ts_ns: int, kind: str, payload: dict[str, str]) -> None: ...


# ---------------------------------------------------------------------------
# Data contracts (frozen, slotted — INV-68 / INV-15)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Position:
    """Current position in a symbol (frozen — INV-68 principle).

    Each position update produces a new immutable snapshot rather than
    mutating in place, enabling deterministic replay from the fill
    sequence.
    """

    symbol: str
    quantity: float  # positive = long, negative = short
    avg_entry_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    last_update_ns: int = 0  # caller-supplied (INV-15)
    regime: str = ""  # regime at time of last fill (BeliefState.regime)
    signal_trust: str = "INTERNAL"  # trust class of originating signal


@dataclass(frozen=True, slots=True)
class PnLAttribution:
    """PnL breakdown per strategy/venue."""

    strategy_id: str
    venue: str
    realized_pnl: float
    unrealized_pnl: float
    total_trades: int
    win_rate: float
    avg_slippage_bps: float
    total_fees: float


@dataclass(frozen=True, slots=True)
class _IntentQueueItem:
    """Priority-ordered execution request (frozen — INV-68).

    Once submitted, the intent is immutable. No field may be changed
    between submission and processing by the orchestrator.
    """

    priority: float  # lower = higher priority
    signal_id: str
    symbol: str
    side: str
    quantity: float
    ts_ns: int  # caller-supplied submission timestamp (INV-15)
    price_limit: float | None = None
    strategy_id: str = "default"
    signal_trust: str = "INTERNAL"  # trust provenance
    regime: str = ""  # BeliefState.regime at submission time
    metadata: tuple[tuple[str, str], ...] = ()  # immutable pairs


class PipelineCoordinator:
    """Async execution pipeline coordinator.

    Manages the full execution lifecycle from intent submission
    through fill confirmation and position reconciliation.

    INV-15 compliance: all timestamp parameters are caller-supplied.
    The coordinator never reads the system clock directly.
    """

    __slots__ = (
        "_lock",
        "_positions",
        "_pnl_by_strategy",
        "_intent_queue",
        "_fill_history",
        "_max_concurrent",
        "_running",
        "_stats",
        "_ledger",
    )

    def __init__(
        self,
        max_concurrent: int = 5,
        ledger: LedgerWriterProtocol | None = None,
    ) -> None:
        self._lock = Lock()
        self._positions: dict[str, Position] = {}
        self._pnl_by_strategy: dict[str, _StrategyPnL] = defaultdict(_StrategyPnL)
        self._intent_queue: list[_IntentQueueItem] = []
        self._fill_history: list[dict[str, str]] = []
        self._max_concurrent = max_concurrent
        self._running = False
        self._stats = _CoordinatorStats()
        self._ledger = ledger

    def start(self) -> None:
        """Start the coordinator."""
        self._running = True
        logger.info("PipelineCoordinator started (max_concurrent=%d)", self._max_concurrent)

    def stop(self) -> None:
        """Stop the coordinator."""
        self._running = False
        logger.info("PipelineCoordinator stopped")

    def submit_intent(
        self,
        *,
        signal_id: str,
        symbol: str,
        side: str,
        quantity: float,
        ts_ns: int,
        price_limit: float | None = None,
        strategy_id: str = "default",
        priority: float = 0.5,
        signal_trust: str = "INTERNAL",
        regime: str = "",
        metadata: tuple[tuple[str, str], ...] = (),
    ) -> bool:
        """Submit an execution intent to the queue.

        Args:
            ts_ns: Submission timestamp (caller-supplied, INV-15).
            signal_trust: Trust class of the originating signal (SignalTrust).
            regime: Current BeliefState.regime at submission time.

        Returns True if accepted, False if rejected (queue full, not running).
        """
        if not self._running:
            return False

        item = _IntentQueueItem(
            priority=priority,
            signal_id=signal_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            ts_ns=ts_ns,
            price_limit=price_limit,
            strategy_id=strategy_id,
            signal_trust=signal_trust,
            regime=regime,
            metadata=metadata,
        )

        with self._lock:
            if len(self._intent_queue) >= 1000:
                logger.warning("Intent queue full, rejecting %s", signal_id)
                return False
            self._intent_queue.append(item)
            self._intent_queue.sort(key=lambda x: x.priority)

        self._stats.intents_submitted += 1
        return True

    def drain_queue(self, max_items: int = 10) -> list[_IntentQueueItem]:
        """Drain up to max_items from the intent queue.

        Called by the runtime kernel tick loop to process pending intents.
        """
        with self._lock:
            batch = self._intent_queue[:max_items]
            self._intent_queue = self._intent_queue[max_items:]
        return batch

    def record_fill(
        self,
        *,
        signal_id: str,
        symbol: str,
        side: str,
        filled_qty: float,
        avg_price: float,
        fees: float,
        venue: str,
        ts_ns: int,
        strategy_id: str = "default",
        slippage_bps: float = 0.0,
        signal_trust: str = "INTERNAL",
        regime: str = "",
        governance_decision_id: str = "",
    ) -> None:
        """Record a fill and update position tracking.

        Args:
            ts_ns: Fill timestamp (caller-supplied, INV-15).
            signal_trust: Trust class of originating signal (SignalTrust).
            regime: BeliefState.regime at fill time.
            governance_decision_id: Governance audit trail.
        """
        with self._lock:
            self._update_position(symbol, side, filled_qty, avg_price, ts_ns, regime, signal_trust)
            self._update_pnl(strategy_id, venue, side, filled_qty, avg_price, fees, slippage_bps)

            self._fill_history.append(
                {
                    "signal_id": signal_id,
                    "symbol": symbol,
                    "side": side,
                    "qty": str(filled_qty),
                    "price": str(avg_price),
                    "fees": str(fees),
                    "venue": venue,
                    "strategy_id": strategy_id,
                    "ts_ns": str(ts_ns),
                    "signal_trust": signal_trust,
                    "regime": regime,
                    "governance_decision_id": governance_decision_id,
                }
            )
            if len(self._fill_history) > 10000:
                self._fill_history = self._fill_history[-10000:]

        self._stats.fills_recorded += 1

        # Audit trail to authority ledger
        if self._ledger:
            try:
                self._ledger.append(
                    ts_ns=ts_ns,
                    kind="FILL_RECORDED",
                    payload={
                        "signal_id": signal_id,
                        "symbol": symbol,
                        "side": side,
                        "filled_qty": str(filled_qty),
                        "avg_price": str(avg_price),
                        "fees": str(fees),
                        "venue": venue,
                        "strategy_id": strategy_id,
                        "signal_trust": signal_trust,
                        "regime": regime,
                        "governance_decision_id": governance_decision_id,
                    },
                )
            except Exception as e:
                logger.error("Ledger write error on fill: %s", e)

    def _update_position(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        ts_ns: int,
        regime: str,
        signal_trust: str,
    ) -> None:
        """Update position tracking for a symbol."""
        current = self._positions.get(symbol)
        if current is None:
            sign = 1.0 if side == "BUY" else -1.0
            self._positions[symbol] = Position(
                symbol=symbol,
                quantity=qty * sign,
                avg_entry_price=price,
                last_update_ns=ts_ns,
                regime=regime,
                signal_trust=signal_trust,
            )
            return

        old_qty = current.quantity
        sign = 1.0 if side == "BUY" else -1.0
        new_qty = old_qty + qty * sign

        if new_qty == 0.0:
            realized = (price - current.avg_entry_price) * qty * (1.0 if old_qty > 0 else -1.0)
            self._positions[symbol] = Position(
                symbol=symbol,
                quantity=0.0,
                avg_entry_price=0.0,
                realized_pnl=current.realized_pnl + realized,
                last_update_ns=ts_ns,
                regime=regime,
                signal_trust=signal_trust,
            )
        elif (old_qty > 0 and new_qty > 0) or (old_qty < 0 and new_qty < 0):
            total_cost = abs(old_qty) * current.avg_entry_price + qty * price
            new_avg = total_cost / abs(new_qty)
            self._positions[symbol] = Position(
                symbol=symbol,
                quantity=new_qty,
                avg_entry_price=new_avg,
                realized_pnl=current.realized_pnl,
                last_update_ns=ts_ns,
                regime=regime,
                signal_trust=signal_trust,
            )
        else:
            close_qty = abs(old_qty)
            realized = (
                (price - current.avg_entry_price) * close_qty * (1.0 if old_qty > 0 else -1.0)
            )
            self._positions[symbol] = Position(
                symbol=symbol,
                quantity=new_qty,
                avg_entry_price=price,
                realized_pnl=current.realized_pnl + realized,
                last_update_ns=ts_ns,
                regime=regime,
                signal_trust=signal_trust,
            )

    def _update_pnl(
        self,
        strategy_id: str,
        venue: str,
        side: str,
        qty: float,
        price: float,
        fees: float,
        slippage_bps: float,
    ) -> None:
        """Update PnL attribution."""
        pnl = self._pnl_by_strategy[strategy_id]
        pnl.total_trades += 1
        pnl.total_fees += fees
        pnl.total_slippage_bps += slippage_bps
        pnl.total_volume += qty * price
        pnl.venue_breakdown[venue] = pnl.venue_breakdown.get(venue, 0) + 1

    def get_position(self, symbol: str) -> Position | None:
        """Get current position for a symbol."""
        with self._lock:
            return self._positions.get(symbol)

    def get_all_positions(self) -> dict[str, Position]:
        """Get all open positions."""
        with self._lock:
            return {s: p for s, p in self._positions.items() if p.quantity != 0.0}

    def get_net_exposure(self) -> float:
        """Total absolute exposure across all positions."""
        with self._lock:
            return sum(
                abs(p.quantity * p.avg_entry_price)
                for p in self._positions.values()
                if p.quantity != 0.0
            )

    def get_pnl_summary(self) -> dict[str, Any]:
        """PnL summary across all strategies."""
        with self._lock:
            total_realized = sum(p.realized_pnl for p in self._positions.values())
            return {
                "total_realized_pnl": total_realized,
                "open_positions": sum(1 for p in self._positions.values() if p.quantity != 0.0),
                "total_trades": self._stats.fills_recorded,
                "strategies": {
                    sid: {
                        "trades": s.total_trades,
                        "fees": round(s.total_fees, 6),
                        "avg_slippage_bps": round(
                            s.total_slippage_bps / s.total_trades if s.total_trades else 0, 2
                        ),
                        "volume": round(s.total_volume, 2),
                    }
                    for sid, s in self._pnl_by_strategy.items()
                },
            }

    @property
    def queue_depth(self) -> int:
        """Number of pending intents in queue."""
        with self._lock:
            return len(self._intent_queue)

    @property
    def stats(self) -> dict[str, int]:
        return {
            "intents_submitted": self._stats.intents_submitted,
            "fills_recorded": self._stats.fills_recorded,
            "queue_depth": self.queue_depth,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _StrategyPnL:
    total_trades: int = 0
    total_fees: float = 0.0
    total_slippage_bps: float = 0.0
    total_volume: float = 0.0
    venue_breakdown: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class _CoordinatorStats:
    intents_submitted: int = 0
    fills_recorded: int = 0


# ---------------------------------------------------------------------------
# Module singleton
# ---------------------------------------------------------------------------

_COORDINATOR: PipelineCoordinator | None = None


def get_pipeline_coordinator(**kwargs: Any) -> PipelineCoordinator:
    """Get or create the singleton PipelineCoordinator."""
    global _COORDINATOR
    if _COORDINATOR is None:
        _COORDINATOR = PipelineCoordinator(**kwargs)
    return _COORDINATOR


__all__ = [
    "PipelineCoordinator",
    "PnLAttribution",
    "Position",
    "get_pipeline_coordinator",
]

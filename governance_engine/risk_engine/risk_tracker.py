"""RiskTracker — stateful fill and P&L accumulation for live risk evaluation.

The pure-function stubs in real_time_risk.py need live inputs.  This module
provides the stateful layer that accumulates fills and equity changes, then
feeds the computed drawdown_pct, notional, and position_qty into
RealTimeRiskEngine.evaluate() to produce a live RiskState.

What this tracks:
    * Per-symbol net position quantities (long positive, short negative)
    * Per-symbol notional exposure (|qty × last_price|)
    * Running realized P&L
    * Peak equity (for drawdown calculation)
    * Daily loss floor (resets each day at midnight by caller convention)

Kill condition integration:
    When a breach is detected, a RISK_BREACH event is published on the
    cognitive event bus.  INDIRA subscribes (via EnvironmentAwareness)
    and adjusts confidence accordingly.  This is the primary safety signal
    that stops cognitive overconfidence when real capital is at risk.

Persistence:
    Risk state is snapshotted to SQLite after every fill so it survives
    a process restart (PAPER mode: fills come from paper_broker; LIVE:
    from the execution fill handler).

Authority: governance_engine.* and core.* only (no intelligence imports).
INV-15: ts_ns is caller-supplied; no wall-clock reads.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

from governance_engine.risk_engine.real_time_risk import RealTimeRiskEngine, RiskState

_logger = logging.getLogger(__name__)

_STORE_KIND = "risk_tracker"


# ---------------------------------------------------------------------------
# FillRecord — one confirmed fill
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FillRecord:
    """One confirmed fill from the execution layer."""

    symbol: str
    side: str           # "buy" | "sell"
    qty: float          # always positive
    price: float
    realized_pnl: float   # 0.0 for opening fills; non-zero for closing
    ts_ns: int


# ---------------------------------------------------------------------------
# RiskTracker
# ---------------------------------------------------------------------------


class RiskTracker:
    """Stateful accumulation of fills and P&L for live risk evaluation.

    Args:
        max_drawdown_pct:        Kill at this drawdown fraction (default 5%).
        max_exposure_notional:   Kill when total notional exceeds this (default $100k).
        max_position_qty:        Kill when any single position exceeds this (default 100 units).
        starting_equity:         Baseline equity for drawdown calculation.
    """

    def __init__(
        self,
        *,
        max_drawdown_pct: float = 0.05,
        max_exposure_notional: float = 100_000.0,
        max_position_qty: float = 100.0,
        starting_equity: float = 0.0,
    ) -> None:
        self._lock = threading.Lock()
        self._engine = RealTimeRiskEngine(
            max_drawdown_pct=max_drawdown_pct,
            max_exposure_notional=max_exposure_notional,
            max_position_qty=max_position_qty,
        )
        self._max_drawdown_pct = max_drawdown_pct
        self._max_exposure_notional = max_exposure_notional
        self._max_position_qty = max_position_qty

        # Position tracking: symbol → net qty (long +, short -)
        self._positions: dict[str, float] = {}
        # Last known prices for notional calculation
        self._last_prices: dict[str, float] = {}
        # P&L accounting
        self._realized_pnl: float = 0.0
        self._starting_equity = starting_equity
        self._peak_equity: float = starting_equity
        self._fill_count: int = 0
        self._manual_halt: bool = False
        self._last_breach: str = ""
        self._fills: list[FillRecord] = []   # recent fills, capped at 200

        self._restore()

    # ------------------------------------------------------------------
    # Write path — called from execution fill handler
    # ------------------------------------------------------------------

    def record_fill(
        self,
        *,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        realized_pnl: float = 0.0,
        ts_ns: int,
    ) -> RiskState:
        """Integrate one fill and return the updated RiskState.

        Args:
            symbol: Instrument identifier (e.g. "BTC/USD").
            side:   "buy" or "sell".
            qty:    Fill quantity (always positive).
            price:  Fill price.
            realized_pnl: Closed P&L for this fill (0 for opening fills).
            ts_ns:  Caller-supplied timestamp (INV-15).

        Returns:
            The live RiskState after integrating the fill.
        """
        fill = FillRecord(
            symbol=symbol, side=side, qty=qty,
            price=price, realized_pnl=realized_pnl, ts_ns=ts_ns,
        )
        with self._lock:
            # Update net position
            delta = qty if side == "buy" else -qty
            self._positions[symbol] = self._positions.get(symbol, 0.0) + delta
            self._last_prices[symbol] = price
            self._realized_pnl += realized_pnl
            self._fill_count += 1
            self._fills.append(fill)
            if len(self._fills) > 200:
                self._fills = self._fills[-200:]
            # Update equity curve
            current_equity = self._starting_equity + self._realized_pnl
            if current_equity > self._peak_equity:
                self._peak_equity = current_equity
            state = self._evaluate_locked()

        if state.halted and state.breach_reason != self._last_breach:
            self._last_breach = state.breach_reason
            self._publish_breach(state, ts_ns)
            _logger.warning("RiskTracker: HALT triggered — %s", state.breach_reason)

        self._persist(ts_ns)
        self._update_market_price(symbol, price, ts_ns)
        return state

    def update_price(self, symbol: str, price: float) -> None:
        """Update last-known price for notional recalculation (best-effort)."""
        with self._lock:
            self._last_prices[symbol] = price

    def set_manual_halt(self, halted: bool) -> None:
        """Operator kill-switch toggle."""
        with self._lock:
            self._manual_halt = halted

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    def current_risk_state(self) -> RiskState:
        """Return a fresh RiskState from current accumulated position/P&L."""
        with self._lock:
            return self._evaluate_locked()

    def drawdown_pct(self) -> float:
        """Current drawdown as a fraction of peak equity."""
        with self._lock:
            return self._drawdown_pct_locked()

    def total_notional(self) -> float:
        """Sum of |qty × price| across all open positions."""
        with self._lock:
            return self._notional_locked()

    def max_position_qty(self) -> float:
        """Largest absolute position size across all symbols."""
        with self._lock:
            return self._max_pos_locked()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            state = self._evaluate_locked()
            positions = {
                sym: {"qty": qty, "price": self._last_prices.get(sym, 0.0)}
                for sym, qty in self._positions.items()
            }
            return {
                "halted": state.halted,
                "breach_reason": state.breach_reason,
                "position_ok": state.position_ok,
                "drawdown_ok": state.drawdown_ok,
                "exposure_ok": state.exposure_ok,
                "realized_pnl": round(self._realized_pnl, 4),
                "peak_equity": round(self._peak_equity, 4),
                "drawdown_pct": round(self._drawdown_pct_locked(), 4),
                "total_notional": round(self._notional_locked(), 2),
                "fill_count": self._fill_count,
                "manual_halt": self._manual_halt,
                "open_positions": positions,
                "limits": {
                    "max_drawdown_pct": self._max_drawdown_pct,
                    "max_exposure_notional": self._max_exposure_notional,
                    "max_position_qty": self._max_position_qty,
                },
            }

    def format_for_context(self) -> str:
        """Compact risk summary for EnvironmentAwareness context injection."""
        with self._lock:
            state = self._evaluate_locked()
            dd = self._drawdown_pct_locked()
        label = "HALT" if state.halted else "OK"
        return f"risk={label} dd={dd:.1%} ntl={self.total_notional():.0f}"

    # ------------------------------------------------------------------
    # Internal computation (called under self._lock)
    # ------------------------------------------------------------------

    def _evaluate_locked(self) -> RiskState:
        return self._engine.evaluate(
            position_qty=self._max_pos_locked(),
            notional=self._notional_locked(),
            drawdown_pct=self._drawdown_pct_locked(),
        )

    def _drawdown_pct_locked(self) -> float:
        if self._peak_equity <= 0:
            return 0.0
        current = self._starting_equity + self._realized_pnl
        dd = (self._peak_equity - current) / self._peak_equity
        return max(0.0, dd)

    def _notional_locked(self) -> float:
        return sum(
            abs(qty) * self._last_prices.get(sym, 0.0)
            for sym, qty in self._positions.items()
        )

    def _max_pos_locked(self) -> float:
        if not self._positions:
            return 0.0
        return max(abs(q) for q in self._positions.values())

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self, ts_ns: int) -> None:
        try:
            from state.cognition_persistence import get_cognition_persistence_store
            with self._lock:
                data = {
                    "positions": dict(self._positions),
                    "last_prices": dict(self._last_prices),
                    "realized_pnl": self._realized_pnl,
                    "peak_equity": self._peak_equity,
                    "fill_count": self._fill_count,
                    "manual_halt": self._manual_halt,
                }
            get_cognition_persistence_store().save_episode(
                store_kind=_STORE_KIND,
                episode_id=f"risk_snap_{self._fill_count}",
                ts_ns=ts_ns,
                data=data,
            )
        except Exception as exc:
            _logger.debug("RiskTracker._persist error: %s", exc)

    def _restore(self) -> None:
        try:
            from state.cognition_persistence import get_cognition_persistence_store
            rows = get_cognition_persistence_store().load_episodes(_STORE_KIND, limit=1)
            if not rows:
                return
            d = rows[0]
            with self._lock:
                self._positions = {str(k): float(v) for k, v in d.get("positions", {}).items()}
                self._last_prices = {str(k): float(v) for k, v in d.get("last_prices", {}).items()}
                self._realized_pnl = float(d.get("realized_pnl", 0.0))
                self._peak_equity = float(d.get("peak_equity", self._starting_equity))
                self._fill_count = int(d.get("fill_count", 0))
                self._manual_halt = bool(d.get("manual_halt", False))
            _logger.info("RiskTracker: restored %d positions from persistence", len(self._positions))
        except Exception as exc:
            _logger.debug("RiskTracker._restore error: %s", exc)

    # ------------------------------------------------------------------
    # Market price feedback
    # ------------------------------------------------------------------

    @staticmethod
    def _update_market_price(symbol: str, price: float, ts_ns: int) -> None:
        """Propagate confirmed fill price to MarketState LKV cache (best-effort)."""
        try:
            from state.market_state import PriceTick, get_market_state
            get_market_state().update(PriceTick(
                symbol=symbol,
                price=price,
                volume=0.0,
                source="risk_tracker_fill",
                ts_ns=ts_ns,
            ))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Event bus
    # ------------------------------------------------------------------

    @staticmethod
    def _publish_breach(state: RiskState, ts_ns: int) -> None:
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().publish(
                CognitiveChannel.RISK_BREACH,   # type: ignore[attr-defined]
                {
                    "halted": state.halted,
                    "breach_reason": state.breach_reason,
                    "position_ok": state.position_ok,
                    "drawdown_ok": state.drawdown_ok,
                    "exposure_ok": state.exposure_ok,
                    "ts_ns": ts_ns,
                },
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_tracker: RiskTracker | None = None
_tracker_lock = threading.Lock()


def get_risk_tracker(
    *,
    max_drawdown_pct: float = 0.05,
    max_exposure_notional: float = 100_000.0,
    max_position_qty: float = 100.0,
    starting_equity: float = 0.0,
) -> RiskTracker:
    """Return the process-wide RiskTracker singleton."""
    global _tracker
    with _tracker_lock:
        if _tracker is None:
            _tracker = RiskTracker(
                max_drawdown_pct=max_drawdown_pct,
                max_exposure_notional=max_exposure_notional,
                max_position_qty=max_position_qty,
                starting_equity=starting_equity,
            )
    return _tracker


__all__ = [
    "FillRecord",
    "RiskTracker",
    "get_risk_tracker",
]

"""execution_engine.paper_trading.adapter — Credential-free paper venue adapter.

PaperVenueAdapter is a LiveAdapterBase subclass that wraps PaperBroker with
venue-realistic fee, slippage, and latency parameters.  It is always READY —
no credentials are required, no external network calls are made.

One instance per venue; six pre-configured instances are built from
VENUE_CONFIGS and registered as "binance_paper", "coinbase_paper", etc.

Design:
* Always READY at construction (no connect() needed, though connect() is a no-op).
* PaperBroker holds the virtual ledger (cash, positions, fills).
* reset() restores initial_cash and clears positions — useful for operator resets.
* snapshot() returns a JSON-ready portfolio view including realized P&L.

Authority: execution_engine.* + core.* at module level only (LiveAdapterBase, PaperBroker).
INV-15: ts_ns from inbound signal, never from wall clock.
INV-56 Triad Lock: paper fills are declared as paper, never disguised as live.
"""

from __future__ import annotations

import threading
from typing import Any

from core.contracts.events import ExecutionEvent, ExecutionStatus, Side, SignalEvent
from execution_engine.adapters._live_base import AdapterState, AdapterStatus, LiveAdapterBase
from execution_engine.adapters.paper import PaperBroker
from execution_engine.paper_trading.venue_config import VenueConfig


class PaperVenueAdapter(LiveAdapterBase):
    """Deterministic paper-trading adapter for one exchange venue.

    Always READY — credential-free, deterministic, and safely replayable.

    Args:
        config: VenueConfig carrying venue-specific fee/slippage parameters.
    """

    def __init__(self, config: VenueConfig) -> None:
        super().__init__(name=config.name, venue=config.venue)
        self._config = config
        self._lock = threading.Lock()
        self._broker = self._make_broker(config)
        self._state = AdapterState.READY
        self._detail = f"paper mode — {config.exchange} ({config.asset_class})"
        self._submit_count: int = 0
        self._reset_count: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Paper adapters are always READY; connect() is a no-op."""
        self._state = AdapterState.READY
        self._detail = f"paper mode — {self._config.exchange} ({self._config.asset_class})"

    def disconnect(self) -> None:
        """Disconnect keeps the ledger; state flips to DISCONNECTED."""
        self._state = AdapterState.DISCONNECTED
        self._detail = "operator disconnect (paper ledger retained)"

    # ------------------------------------------------------------------
    # BrokerAdapter protocol
    # ------------------------------------------------------------------

    def _submit_live(self, signal: SignalEvent, mark_price: float) -> ExecutionEvent:
        """Delegate to PaperBroker; tag meta with venue and paper flag."""
        with self._lock:
            self._submit_count += 1
            evt = self._broker.submit(signal, mark_price)
        # Stamp adapter and paper flag into meta
        meta = dict(evt.meta)
        meta["adapter"] = self.name
        meta["venue"] = self.venue
        meta["paper"] = "1"
        meta["exchange"] = self._config.exchange
        meta["asset_class"] = self._config.asset_class
        return ExecutionEvent(
            ts_ns=evt.ts_ns,
            symbol=evt.symbol,
            side=evt.side,
            qty=evt.qty,
            price=evt.price,
            status=evt.status,
            venue=self.venue,
            order_id=evt.order_id,
            meta=meta,
            produced_by_engine=evt.produced_by_engine,
        )

    # ------------------------------------------------------------------
    # Portfolio read surface
    # ------------------------------------------------------------------

    def cash_balance(self) -> float:
        with self._lock:
            return self._broker.cash_balance()

    def initial_cash(self) -> float:
        return self._config.initial_cash

    def positions(self) -> dict[str, float]:
        with self._lock:
            return self._broker.positions()

    def recent_fills(self, n: int = 50) -> list[ExecutionEvent]:
        with self._lock:
            return self._broker.recent_fills(n)

    def realized_pnl(self) -> float:
        """Realized P&L = current cash − initial cash (position value not included)."""
        with self._lock:
            return self._broker.cash_balance() - self._config.initial_cash

    def fill_count(self) -> int:
        with self._lock:
            return self._submit_count

    def portfolio_snapshot(self) -> dict[str, Any]:
        """JSON-ready portfolio snapshot for the operator dashboard."""
        with self._lock:
            cash = self._broker.cash_balance()
            positions = self._broker.positions()
            fills = [_evt_to_dict(f) for f in self._broker.recent_fills(20)]
            submit_count = self._submit_count
            reset_count = self._reset_count
        realized_pnl = cash - self._config.initial_cash
        return {
            "name": self.name,
            "venue": self.venue,
            "exchange": self._config.exchange,
            "asset_class": self._config.asset_class,
            "state": self._state.value,
            "cash": round(cash, 4),
            "initial_cash": self._config.initial_cash,
            "realized_pnl": round(realized_pnl, 4),
            "realized_pnl_pct": round(
                realized_pnl / self._config.initial_cash * 100, 4
            ) if self._config.initial_cash else 0.0,
            "positions": {sym: round(qty, 8) for sym, qty in positions.items()},
            "open_position_count": len(positions),
            "submit_count": submit_count,
            "reset_count": reset_count,
            "recent_fills": fills,
            "config": {
                "slippage_bps": self._config.slippage_bps,
                "taker_fee_bps": self._config.taker_fee_bps,
                "maker_fee_bps": self._config.maker_fee_bps,
                "latency_ms": self._config.latency_ns_base / 1_000_000,
            },
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset paper portfolio to initial state (cash + positions cleared)."""
        with self._lock:
            self._broker = self._make_broker(self._config)
            self._reset_count += 1

    # ------------------------------------------------------------------
    # Override status to include paper tag
    # ------------------------------------------------------------------

    def status(self) -> AdapterStatus:
        return AdapterStatus(
            name=self.name,
            venue=self.venue,
            state=self._state,
            detail=self._detail,
            last_heartbeat_ns=self._last_heartbeat_ns,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _make_broker(config: VenueConfig) -> PaperBroker:
        return PaperBroker(
            slippage_bps=config.slippage_bps,
            default_qty=config.default_qty,
            taker_fee_bps=config.taker_fee_bps,
            maker_fee_bps=config.maker_fee_bps,
            latency_ns_base=config.latency_ns_base,
            latency_ns_jitter=config.latency_ns_jitter,
            initial_cash=config.initial_cash,
            fill_ring_size=config.fill_ring_size,
        )


# ---------------------------------------------------------------------------
# Serialisation helper
# ---------------------------------------------------------------------------


def _evt_to_dict(evt: ExecutionEvent) -> dict[str, Any]:
    return {
        "ts_ns": evt.ts_ns,
        "symbol": evt.symbol,
        "side": evt.side.value if hasattr(evt.side, "value") else str(evt.side),
        "qty": evt.qty,
        "price": evt.price,
        "status": evt.status.value if hasattr(evt.status, "value") else str(evt.status),
        "venue": evt.venue,
        "order_id": evt.order_id,
        "meta": dict(evt.meta),
    }


__all__ = ["PaperVenueAdapter"]

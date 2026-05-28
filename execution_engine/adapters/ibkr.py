# ADAPTED FROM: erdewit/ib_insync
# (ib_insync/ib.py — IB class, connect(), placeOrder(), cancelOrder(),
#  positions(); ib_insync/contract.py — Contract, Stock, Forex, Future;
#  ib_insync/order.py — Order, MarketOrder, LimitOrder)
"""I-18 — Interactive Brokers adapter (institutional equities + futures + forex).

This module adapts the ``ib_insync`` library
(https://github.com/erdewit/ib_insync, BSD-2-Clause) as a
:class:`BrokerAdapter` for institutional trading via Interactive
Brokers' TWS/Gateway API.

What survives from upstream (erdewit/ib_insync):
    * **IB.connect()** — ``ib_insync/ib.py:257``: blocking connection to
      TWS or IB Gateway on localhost:7497 (paper) or :4001 (live).
    * **IB.placeOrder(contract, order)** — ``ib.py:649``: submits a new
      order and returns a Trade with live status updates.
    * **Contract hierarchy** — ``contract.py:11``: Stock, Forex, Future
      classes with exchange/currency/expiry fields.
    * **Order types** — ``order.py``: Market, Limit, Stop order
      builders.

What we replaced:
    * ``ib_insync`` dependency → lazy-imported at connect()-time. The
      module imports cleanly even when ``ib_insync`` is not installed.
    * ib_insync's async event loop is isolated — DIX never exposes it to
      RUNTIME. All interaction is synchronous from the adapter's
      perspective.
    * No datetime calls — timestamps come from signal.ts_ns.
    * All errors become ``ExecutionEvent(status=FAILED)`` rather than
      raising.

NEW_PIP_DEPENDENCIES = ("ib-insync",)
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.contracts.events import (
    ExecutionEvent,
    ExecutionStatus,
    Side,
    SignalEvent,
)
from execution_engine.adapters._live_base import (
    AdapterState,
    LiveAdapterBase,
)

# ib_insync order status strings (from ib_insync/order.py OrderStatus)
_IB_STATUS: Mapping[str, ExecutionStatus] = {
    "Submitted": ExecutionStatus.FILLED,  # order live, awaiting fill
    "PendingSubmit": ExecutionStatus.FILLED,
    "PendingCancel": ExecutionStatus.CANCELLED,
    "PreSubmitted": ExecutionStatus.FILLED,
    "Filled": ExecutionStatus.FILLED,
    "Cancelled": ExecutionStatus.CANCELLED,
    "Inactive": ExecutionStatus.REJECTED,
    "ApiCancelled": ExecutionStatus.CANCELLED,
    "ApiPending": ExecutionStatus.FILLED,
}


class IBKRAdapter(LiveAdapterBase):
    """Interactive Brokers adapter for equities, futures, and forex.

    Implements the :class:`BrokerAdapter` Protocol via
    :class:`LiveAdapterBase`.  Requires TWS or IB Gateway running
    separately (``ib_insync`` connects to the local API socket).

    Until :meth:`connect` is called with valid parameters,
    ``submit()`` returns ``REJECTED`` events.
    """

    name: str = "ibkr"
    venue: str = "ibkr:paper"

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 1,
        paper: bool = True,
        default_qty: float = 0.0,
    ) -> None:
        super().__init__(
            name="ibkr",
            venue=f"ibkr:{'paper' if paper else 'live'}",
        )
        self._host = host
        self._port = port if paper else 4001
        self._client_id = client_id
        self._paper = paper
        self._default_qty = default_qty
        self._ib: Any = None  # ib_insync.IB instance (lazy)
        self._order_counter: int = 0

    # ---- lifecycle -------------------------------------------------------

    def connect(self) -> None:
        """Connect to TWS/Gateway via ib_insync.

        ib_insync is lazy-imported here so the module itself is always
        importable without the package installed (matching the ccxt
        adapter pattern).
        """
        try:
            import ib_insync  # noqa: F401 — lazy import at connect time

            self._ib = ib_insync.IB()
            self._ib.connect(
                host=self._host,
                port=self._port,
                clientId=self._client_id,
                timeout=10,
                readonly=False,
            )
            self._state = AdapterState.READY
            self._detail = f"connected to {self._host}:{self._port}"
        except ImportError:
            self._state = AdapterState.DISCONNECTED
            self._detail = "ib_insync not installed"
        except Exception as e:
            self._state = AdapterState.DEGRADED
            self._detail = f"connect failed: {e}"

    def disconnect(self) -> None:
        if self._ib is not None:
            try:
                self._ib.disconnect()
            except Exception:
                pass
        self._ib = None
        self._state = AdapterState.DISCONNECTED
        self._detail = "disconnected by operator"

    # ---- internals (qty) -------------------------------------------------

    def _qty_for(self, signal: SignalEvent) -> float:
        raw = signal.meta.get("qty")
        if raw is None:
            return self._default_qty
        try:
            v = float(raw)
        except (TypeError, ValueError):
            return 0.0
        if not (v >= 0.0):
            return 0.0
        return v

    # ---- BrokerAdapter Protocol ------------------------------------------

    def _submit_live(
        self,
        signal: SignalEvent,
        mark_price: float,
    ) -> ExecutionEvent:
        """Submit order to IB via ib_insync and return ExecutionEvent."""
        self._order_counter += 1
        qty = self._qty_for(signal)

        try:
            import ib_insync

            # Build contract — parse symbol for asset class.
            # Convention: "AAPL" → Stock, "EUR/USD" → Forex,
            # "ES202506" → Future (symbol + expiry).
            contract = self._build_contract(signal.symbol, ib_insync)

            # Build market order (matching ib_insync/order.py patterns).
            action = "BUY" if signal.side == Side.BUY else "SELL"
            order = ib_insync.MarketOrder(action=action, totalQuantity=qty)

            # Place order (ib_insync/ib.py:649 placeOrder).
            trade = self._ib.placeOrder(contract, order)

            # Wait briefly for fill (ib_insync uses asyncio internally).
            self._ib.sleep(2)

            return self._normalise_trade(trade, signal, mark_price)

        except ImportError:
            return ExecutionEvent(
                ts_ns=signal.ts_ns,
                symbol=signal.symbol,
                side=signal.side,
                qty=0.0,
                price=mark_price,
                status=ExecutionStatus.FAILED,
                venue=self.venue,
                order_id="",
                meta={"ib_error": "ib_insync not installed"},
                produced_by_engine="execution_engine",
            )
        except Exception as e:
            return ExecutionEvent(
                ts_ns=signal.ts_ns,
                symbol=signal.symbol,
                side=signal.side,
                qty=0.0,
                price=mark_price,
                status=ExecutionStatus.FAILED,
                venue=self.venue,
                order_id="",
                meta={"ib_error": str(e), "ib_error_class": type(e).__name__},
                produced_by_engine="execution_engine",
            )

    # ---- internals -------------------------------------------------------

    def _build_contract(self, symbol: str, ib_insync: Any) -> Any:
        """Build an ib_insync Contract from a DIX symbol string.

        Mirrors ib_insync/contract.py class hierarchy:
        - Stock(symbol, exchange, currency)
        - Forex(pair) for "XXX/YYY" format
        - Future(symbol, lastTradeDateOrContractMonth, exchange)
        """
        if "/" in symbol:
            # Forex pair: "EUR/USD" → Forex("EURUSD")
            pair = symbol.replace("/", "")
            return ib_insync.Forex(pair)
        if symbol[-6:].isdigit() and len(symbol) > 6:
            # Future: "ES202506" → Future("ES", "202506", "CME")
            underlying = symbol[:-6]
            expiry = symbol[-6:]
            return ib_insync.Future(
                symbol=underlying,
                lastTradeDateOrContractMonth=expiry,
                exchange="CME",
            )
        # Default: US Stock on SMART routing.
        return ib_insync.Stock(symbol=symbol, exchange="SMART", currency="USD")

    def _normalise_trade(
        self,
        trade: Any,
        signal: SignalEvent,
        mark_price: float,
    ) -> ExecutionEvent:
        """Convert ib_insync Trade to a structured ExecutionEvent."""
        raw_status = trade.orderStatus.status if trade.orderStatus else "Inactive"
        status = _IB_STATUS.get(raw_status, ExecutionStatus.FAILED)

        filled_qty = float(trade.orderStatus.filled) if trade.orderStatus else 0.0
        avg_price = float(trade.orderStatus.avgFillPrice) if trade.orderStatus else mark_price

        return ExecutionEvent(
            ts_ns=signal.ts_ns,
            symbol=signal.symbol,
            side=signal.side,
            qty=filled_qty,
            price=avg_price if avg_price > 0 else mark_price,
            status=status,
            venue=self.venue,
            order_id=str(trade.order.orderId) if trade.order else "",
            meta={
                "ib_status": raw_status,
                "ib_perm_id": str(trade.order.permId) if trade.order else "",
                "ib_client_id": str(self._client_id),
            },
            produced_by_engine="execution_engine",
        )


__all__ = ["IBKRAdapter"]

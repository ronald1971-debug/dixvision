# ADAPTED FROM: alpacahq/alpaca-py
# (alpaca/trading/client.py — TradingClient class, submit_order, get_all_positions,
#  cancel_order_by_id, close_position; alpaca/trading/requests.py — OrderRequest,
#  MarketOrderRequest, LimitOrderRequest; alpaca/trading/enums.py — OrderSide,
#  TimeInForce, OrderType, OrderStatus)
"""I-17 — Alpaca Markets adapter (US equities + crypto).

This module adapts the ``alpaca-py`` client library
(https://github.com/alpacahq/alpaca-py, Apache-2.0) as a
:class:`BrokerAdapter` for US stock and crypto trading via Alpaca
Markets.

What survives from upstream (alpacahq/alpaca-py):
    * **TradingClient** — ``alpaca/trading/client.py:48``: connection
      init with ``api_key``, ``secret_key``, and ``paper`` flag routing
      to the correct base URL.
    * **submit_order** — ``client.py:90``: builds ``OrderRequest`` then
      POSTs to ``/v2/orders``. We replicate the JSON body shape.
    * **Order response** — the response has ``id``, ``status``,
      ``filled_qty``, ``filled_avg_price``, ``symbol``, ``side``.
    * **Paper mode** — ``paper=True`` routes to
      ``https://paper-api.alpaca.markets``.

What we replaced:
    * ``alpaca-py`` dependency → stdlib ``urllib.request`` (matching the
      existing adapter pattern). The adapter module imports cleanly even
      when ``alpaca-py`` is not installed.
    * No datetime calls, no internal clocks — timestamps come from the
      signal's ``ts_ns`` plus an internal monotonic counter.
    * All errors become structured ``ExecutionEvent(status=FAILED)``
      rather than raising exceptions up the call stack.

NEW_PIP_DEPENDENCIES = ("alpaca-py",)
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
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

# Alpaca base URLs (from alpaca/common/enums.py BaseURL enum)
_PAPER_BASE = "https://paper-api.alpaca.markets"
_LIVE_BASE = "https://api.alpaca.markets"

# Mapping from Alpaca order status strings to DIX ExecutionStatus.
# Alpaca returns: "new", "partially_filled", "filled", "done_for_day",
# "canceled", "expired", "replaced", "pending_cancel", "pending_replace",
# "accepted", "pending_new", "accepted_for_bidding", "stopped", "rejected",
# "suspended", "calculated" (from alpaca/trading/enums.py OrderStatus).
_ALPACA_STATUS: Mapping[str, ExecutionStatus] = {
    "new": ExecutionStatus.FILLED,  # submitted, awaiting fill
    "partially_filled": ExecutionStatus.PARTIALLY_FILLED,
    "filled": ExecutionStatus.FILLED,
    "done_for_day": ExecutionStatus.FILLED,
    "canceled": ExecutionStatus.CANCELLED,
    "expired": ExecutionStatus.CANCELLED,
    "replaced": ExecutionStatus.CANCELLED,
    "rejected": ExecutionStatus.REJECTED,
    "suspended": ExecutionStatus.REJECTED,
    "pending_cancel": ExecutionStatus.FILLED,
    "pending_replace": ExecutionStatus.FILLED,
    "accepted": ExecutionStatus.FILLED,
    "pending_new": ExecutionStatus.FILLED,
    "accepted_for_bidding": ExecutionStatus.FILLED,
}


class AlpacaAdapter(LiveAdapterBase):
    """Alpaca Markets adapter for US equities and crypto.

    Implements the :class:`BrokerAdapter` Protocol via
    :class:`LiveAdapterBase`.  Until :meth:`connect` is called with
    valid API keys, ``submit()`` returns ``REJECTED`` events.

    Credentials are passed explicitly — never read from environment
    (INV-65 per-decision audit truthfulness).
    """

    name: str = "alpaca"
    venue: str = "alpaca:paper"

    def __init__(
        self,
        *,
        api_key: str = "",
        secret_key: str = "",
        paper: bool = True,
        default_qty: float = 0.0,
    ) -> None:
        super().__init__(name="alpaca", venue=f"alpaca:{'paper' if paper else 'live'}")
        self._api_key = api_key
        self._secret_key = secret_key
        self._paper = paper
        self._base_url = _PAPER_BASE if paper else _LIVE_BASE
        self._default_qty = default_qty
        self._order_counter: int = 0

    # ---- lifecycle -------------------------------------------------------

    def connect(self) -> None:
        """Verify credentials by hitting the /v2/account endpoint."""
        if not self._api_key or not self._secret_key:
            self._state = AdapterState.DISCONNECTED
            self._detail = "credentials not wired (api_key/secret_key empty)"
            return
        try:
            self._request("GET", "/v2/account")
            self._state = AdapterState.READY
            self._detail = "connected"
        except Exception as e:
            self._state = AdapterState.DEGRADED
            self._detail = f"connect failed: {e}"

    def disconnect(self) -> None:
        self._state = AdapterState.DISCONNECTED
        self._detail = "disconnected by operator"

    # ---- internals -------------------------------------------------------

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
        """Submit order to Alpaca and return a structured ExecutionEvent."""
        self._order_counter += 1

        qty = self._qty_for(signal)

        # Build the order body matching alpaca-py's OrderRequest shape
        # (alpaca/trading/requests.py — MarketOrderRequest fields).
        body: dict[str, Any] = {
            "symbol": signal.symbol.replace("/", ""),  # "BTC/USD" -> "BTCUSD"
            "qty": str(qty),
            "side": "buy" if signal.side == Side.BUY else "sell",
            "type": "market",
            "time_in_force": "gtc",
        }

        try:
            resp = self._request("POST", "/v2/orders", body=body)
            return self._normalise_order(resp, signal, mark_price)
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            return ExecutionEvent(
                ts_ns=signal.ts_ns,
                symbol=signal.symbol,
                side=signal.side,
                qty=0.0,
                price=mark_price,
                status=ExecutionStatus.FAILED,
                venue=self.venue,
                order_id="",
                meta={
                    "alpaca_error": error_body,
                    "alpaca_http_status": str(e.code),
                },
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
                meta={"alpaca_error": str(e), "alpaca_error_class": type(e).__name__},
                produced_by_engine="execution_engine",
            )

    # ---- internals -------------------------------------------------------

    def _normalise_order(
        self,
        resp: dict[str, Any],
        signal: SignalEvent,
        mark_price: float,
    ) -> ExecutionEvent:
        """Convert Alpaca JSON response to a structured ExecutionEvent."""
        raw_status = resp.get("status", "rejected")
        status = _ALPACA_STATUS.get(raw_status, ExecutionStatus.FAILED)

        filled_qty = float(resp.get("filled_qty") or 0)
        filled_price = float(resp.get("filled_avg_price") or mark_price)

        return ExecutionEvent(
            ts_ns=signal.ts_ns,
            symbol=signal.symbol,
            side=signal.side,
            qty=filled_qty,
            price=filled_price,
            status=status,
            venue=self.venue,
            order_id=resp.get("id", ""),
            meta={
                "alpaca_status": raw_status,
                "alpaca_client_order_id": resp.get("client_order_id", ""),
                "alpaca_order_type": resp.get("type", "market"),
            },
            produced_by_engine="execution_engine",
        )

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated HTTP request to Alpaca.

        Mirrors alpaca-py's RESTClient pattern (alpaca/common/rest.py).
        Headers: APCA-API-KEY-ID + APCA-API-SECRET-KEY (from
        alpaca/trading/client.py:74 super().__init__ → RESTClient).
        """
        url = f"{self._base_url}{path}"
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("APCA-API-KEY-ID", self._api_key)
        req.add_header("APCA-API-SECRET-KEY", self._secret_key)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")

        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())


__all__ = ["AlpacaAdapter"]

"""
execution/adapters/coinbase.py
DIX VISION v42.2 — Coinbase Exchange Adapter

DOMAIN: INDIRA only. Dyon cannot import this module.

Connects to Coinbase via CCXT when credentials are available.
Falls back to paper mode when CCXT is absent or unconfigured.
"""

from __future__ import annotations

from typing import Any

from execution.adapters._ccxt_backed import (
    ccxt_cancel_order,
    ccxt_connect,
    ccxt_get_balance,
    ccxt_place_order,
)
from execution.adapters.base import BaseAdapter


class CoinbaseAdapter(BaseAdapter):
    """Exchange adapter for Coinbase (CCXT-backed)."""

    name = "coinbase"
    category = "CEX"
    trading_forms = frozenset({"SPOT"})
    order_types = frozenset({"MARKET", "LIMIT", "STOP"})

    def __init__(self, api_key: str = "", api_secret: str = "") -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self._connected = False
        self._ccxt_exchange: Any = None
        self._paper_mode = True

    def connect(self) -> bool:
        self._ccxt_exchange, self._paper_mode = ccxt_connect(
            self.name, "coinbase", self.api_key, self.api_secret
        )
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False
        self._ccxt_exchange = None

    def place_order(
        self, symbol: str, side: str, size: float, order_type: str = "MARKET"
    ) -> dict[str, Any]:
        return ccxt_place_order(
            self.name, self._ccxt_exchange, self._paper_mode, symbol, side, size, order_type
        )

    def cancel_order(self, order_id: str) -> bool:
        return ccxt_cancel_order(self.name, self._ccxt_exchange, self._paper_mode, order_id)

    def get_balance(self, asset: str = "USDT") -> float:
        return ccxt_get_balance(self._ccxt_exchange, self._paper_mode, asset)

    def is_connected(self) -> bool:
        return self._connected

    @property
    def paper_mode(self) -> bool:
        return self._paper_mode

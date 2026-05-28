"""Alpaca platform integration (Paper-S7).

Read-only adapter for Alpaca Markets: account, positions,
market data, and paper trading state monitoring.

__capability_tier__ = 0
__forbidden_tiers__ = (5,)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__capability_tier__ = 0
__forbidden_tiers__ = (5,)


@dataclass(frozen=True, slots=True)
class AlpacaPosition:
    """An Alpaca position."""

    asset_id: str
    symbol: str
    side: str  # "long" | "short"
    qty: float
    avg_entry_price: float
    market_value: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    change_today: float


@dataclass(frozen=True, slots=True)
class AlpacaAccount:
    """Alpaca account info."""

    account_id: str
    status: str  # "ACTIVE" | "INACTIVE"
    equity: float
    cash: float
    buying_power: float
    portfolio_value: float
    pattern_day_trader: bool
    trading_blocked: bool
    account_blocked: bool
    daytrade_count: int
    currency: str


@dataclass(frozen=True, slots=True)
class AlpacaBar:
    """Alpaca OHLCV bar."""

    symbol: str
    ts_ns: int
    open_price: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float
    trade_count: int


class AlpacaAdapter:
    """Read-only adapter for Alpaca Markets.

    Reads account state, positions, and market data.
    Supports both live and paper trading accounts (read-only).
    Never places orders.
    """

    def __init__(
        self,
        *,
        api_key: str = "",
        api_secret: str = "",
        paper: bool = True,
    ) -> None:
        self._key = api_key
        self._secret = api_secret
        self._paper = paper
        base = "https://paper-api.alpaca.markets" if paper else "https://api.alpaca.markets"
        self._base_url = base

    def fetch_account(self) -> AlpacaAccount | None:
        """Fetch account info."""
        return None

    def fetch_positions(self) -> list[AlpacaPosition]:
        """Fetch all open positions."""
        return []

    def fetch_bars(
        self,
        *,
        symbol: str,
        timeframe: str = "1Day",
        limit: int = 100,
    ) -> list[AlpacaBar]:
        """Fetch historical bars."""
        return []

    def fetch_latest_quote(self, *, symbol: str) -> dict[str, Any]:
        """Fetch latest quote for a symbol."""
        return {}

    def fetch_order_history(self, *, status: str = "all", limit: int = 50) -> list[dict[str, Any]]:
        """Fetch order history (monitoring only)."""
        return []

    def fetch_portfolio_history(
        self, *, period: str = "1M", timeframe: str = "1D"
    ) -> dict[str, Any]:
        """Fetch portfolio performance history."""
        return {}

"""MetaTrader 5 platform integration (Paper-S4).

Read-only adapter for MT5 terminal data: positions, account info,
history, and signals from Expert Advisors.

__capability_tier__ = 0
__forbidden_tiers__ = (5,)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__capability_tier__ = 0
__forbidden_tiers__ = (5,)


@dataclass(frozen=True, slots=True)
class MT5Position:
    """An MT5 position snapshot."""

    ticket: int
    symbol: str
    side: str  # "buy" | "sell"
    volume: float
    price_open: float
    price_current: float
    profit: float
    swap: float
    comment: str
    magic_number: int
    ts_open_ns: int


@dataclass(frozen=True, slots=True)
class MT5AccountInfo:
    """MT5 account state snapshot."""

    login: int
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level_pct: float
    profit: float
    leverage: int
    currency: str
    server: str


@dataclass(frozen=True, slots=True)
class MT5Signal:
    """Signal from MT5 Expert Advisor."""

    ea_name: str
    symbol: str
    side: str
    entry_price: float
    stop_loss: float
    take_profit: float
    volume: float
    comment: str
    magic_number: int
    ts_ns: int


class MT5Adapter:
    """Read-only adapter for MetaTrader 5.

    Connects to MT5 terminal via bridge to read positions,
    account info, and EA signals. Never places orders.
    """

    def __init__(self, *, server: str = "", login: int = 0) -> None:
        self._server = server
        self._login = login
        self._connected = False

    def fetch_positions(self) -> list[MT5Position]:
        """Fetch current open positions from MT5."""
        return []

    def fetch_account_info(self) -> MT5AccountInfo | None:
        """Fetch account info from MT5."""
        return None

    def fetch_signals(self, *, since_ts_ns: int = 0, limit: int = 50) -> list[MT5Signal]:
        """Fetch EA signals from MT5."""
        return []

    def fetch_history(
        self,
        *,
        symbol: str = "",
        since_ts_ns: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch trade history from MT5."""
        return []

    def fetch_market_data(
        self, *, symbol: str, timeframe: str = "H1", bars: int = 100
    ) -> list[dict[str, Any]]:
        """Fetch OHLCV bars from MT5."""
        return []

    @property
    def is_connected(self) -> bool:
        """Check connection status."""
        return self._connected

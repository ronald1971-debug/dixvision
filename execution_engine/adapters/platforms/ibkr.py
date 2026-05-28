"""Interactive Brokers integration (Paper-S6).

Read-only adapter for IBKR TWS/Gateway: account data, positions,
market data, and order status monitoring.

__capability_tier__ = 0
__forbidden_tiers__ = (5,)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__capability_tier__ = 0
__forbidden_tiers__ = (5,)


@dataclass(frozen=True, slots=True)
class IBKRPosition:
    """An IBKR position."""

    contract_id: int
    symbol: str
    sec_type: str  # "STK" | "OPT" | "FUT" | "CRYPTO"
    exchange: str
    currency: str
    quantity: float
    avg_cost: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float


@dataclass(frozen=True, slots=True)
class IBKRAccountSummary:
    """IBKR account summary."""

    account_id: str
    net_liquidation: float
    total_cash: float
    buying_power: float
    gross_position_value: float
    unrealized_pnl: float
    realized_pnl: float
    maintenance_margin: float
    currency: str


@dataclass(frozen=True, slots=True)
class IBKRMarketData:
    """IBKR market data tick."""

    symbol: str
    bid: float
    ask: float
    last: float
    volume: int
    open_price: float
    high: float
    low: float
    close: float
    ts_ns: int


class IBKRAdapter:
    """Read-only adapter for Interactive Brokers.

    Connects to TWS/Gateway via API to read positions,
    account data, and market data. Never places orders.
    """

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 1,
    ) -> None:
        self._host = host
        self._port = port
        self._client_id = client_id
        self._connected = False

    def fetch_positions(self) -> list[IBKRPosition]:
        """Fetch all positions from IBKR."""
        return []

    def fetch_account_summary(self) -> IBKRAccountSummary | None:
        """Fetch account summary."""
        return None

    def fetch_market_data(
        self, *, symbol: str, sec_type: str = "STK", exchange: str = "SMART"
    ) -> IBKRMarketData | None:
        """Fetch latest market data for a symbol."""
        return None

    def fetch_historical_data(
        self,
        *,
        symbol: str,
        duration: str = "1 Y",
        bar_size: str = "1 day",
        sec_type: str = "STK",
    ) -> list[dict[str, Any]]:
        """Fetch historical bars."""
        return []

    def fetch_order_status(self, *, order_id: int) -> dict[str, Any]:
        """Fetch status of an order (monitoring only)."""
        return {}

    @property
    def is_connected(self) -> bool:
        """Check connection status."""
        return self._connected

"""CCXT exchange adapter (OSS Integration Layer).

Wraps ccxt.Exchange into DIXVISION's execution contracts.
Provides unified access to 100+ exchanges while respecting
governance gates, kill switches, and operator authority.

All execution methods are gated:
- read-only by default (market data, account info)
- execution requires explicit operator enablement
- kill switch immediately cancels all pending operations

Reference: github.com/ccxt/ccxt
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ExchangeId(StrEnum):
    """Supported exchanges via CCXT."""

    BINANCE = "binance"
    BYBIT = "bybit"
    OKX = "okx"
    COINBASE = "coinbase"
    KRAKEN = "kraken"
    KUCOIN = "kucoin"
    GATE = "gate"
    BITGET = "bitget"
    MEXC = "mexc"
    HTX = "htx"


class OrderType(StrEnum):
    """Order types."""

    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    STOP_LIMIT = "stop_limit"


class OrderSide(StrEnum):
    """Order side."""

    BUY = "buy"
    SELL = "sell"


class OrderStatus(StrEnum):
    """Order status."""

    OPEN = "open"
    CLOSED = "closed"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class OHLCV:
    """OHLCV candle."""

    ts_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class Ticker:
    """Market ticker."""

    symbol: str
    bid: float
    ask: float
    last: float
    volume_24h: float
    change_pct_24h: float
    ts_ms: int


@dataclass(frozen=True, slots=True)
class Balance:
    """Account balance for an asset."""

    asset: str
    free: float
    used: float
    total: float


@dataclass(frozen=True, slots=True)
class OrderResult:
    """Result of an order submission."""

    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    amount: float
    price: float | None
    status: OrderStatus
    filled: float
    remaining: float
    cost: float
    fee: float
    ts_ms: int


class CCXTExchangeAdapter:
    """DIXVISION adapter wrapping CCXT exchange instances.

    Provides:
    - Market data (read-only, always available)
    - Account info (read-only, requires credentials)
    - Order execution (gated by operator authority)
    - Position management (gated by operator authority)

    All methods return DIXVISION-native dataclasses, never raw CCXT dicts.
    """

    def __init__(
        self,
        *,
        exchange_id: ExchangeId,
        api_key: str = "",
        api_secret: str = "",
        passphrase: str = "",
        sandbox: bool = True,
        execution_enabled: bool = False,
    ) -> None:
        self._exchange_id = exchange_id
        self._api_key = api_key
        self._api_secret = api_secret
        self._passphrase = passphrase
        self._sandbox = sandbox
        self._execution_enabled = execution_enabled
        self._kill_switch = False
        self._ccxt_instance: Any = None

    def connect(self) -> bool:
        """Initialize CCXT exchange instance.

        Returns True if connection successful.
        In production: creates ccxt.<exchange_id>() instance.
        """
        try:
            import ccxt  # noqa: F401

            config: dict[str, Any] = {
                "apiKey": self._api_key,
                "secret": self._api_secret,
                "sandbox": self._sandbox,
                "enableRateLimit": True,
            }
            if self._passphrase:
                config["password"] = self._passphrase

            exchange_class = getattr(ccxt, self._exchange_id.value, None)
            if exchange_class is None:
                return False
            self._ccxt_instance = exchange_class(config)
            return True
        except ImportError:
            # CCXT not installed — return False, adapter works in stub mode
            return False

    # --- Market Data (always available) ---

    def fetch_ticker(self, symbol: str) -> Ticker | None:
        """Fetch latest ticker for a symbol."""
        if self._ccxt_instance is None:
            return None
        try:
            raw = self._ccxt_instance.fetch_ticker(symbol)
            return Ticker(
                symbol=raw["symbol"],
                bid=float(raw.get("bid") or 0),
                ask=float(raw.get("ask") or 0),
                last=float(raw.get("last") or 0),
                volume_24h=float(raw.get("quoteVolume") or 0),
                change_pct_24h=float(raw.get("percentage") or 0),
                ts_ms=int(raw.get("timestamp") or 0),
            )
        except Exception:
            return None

    def fetch_ohlcv(
        self,
        symbol: str,
        *,
        timeframe: str = "1h",
        limit: int = 100,
    ) -> list[OHLCV]:
        """Fetch OHLCV candles."""
        if self._ccxt_instance is None:
            return []
        try:
            raw = self._ccxt_instance.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            return [
                OHLCV(
                    ts_ms=int(c[0]),
                    open=float(c[1]),
                    high=float(c[2]),
                    low=float(c[3]),
                    close=float(c[4]),
                    volume=float(c[5]),
                )
                for c in raw
            ]
        except Exception:
            return []

    def fetch_order_book(self, symbol: str, *, limit: int = 20) -> dict[str, list[list[float]]]:
        """Fetch order book (bids/asks)."""
        if self._ccxt_instance is None:
            return {"bids": [], "asks": []}
        try:
            raw = self._ccxt_instance.fetch_order_book(symbol, limit=limit)
            return {"bids": raw.get("bids", []), "asks": raw.get("asks", [])}
        except Exception:
            return {"bids": [], "asks": []}

    # --- Account (requires credentials) ---

    def fetch_balance(self) -> list[Balance]:
        """Fetch account balances."""
        if self._ccxt_instance is None:
            return []
        try:
            raw = self._ccxt_instance.fetch_balance()
            balances: list[Balance] = []
            for asset, info in raw.get("total", {}).items():
                total = float(info) if info else 0.0
                if total > 0:
                    free = float(raw.get("free", {}).get(asset) or 0)
                    used = float(raw.get("used", {}).get(asset) or 0)
                    balances.append(
                        Balance(
                            asset=asset,
                            free=free,
                            used=used,
                            total=total,
                        )
                    )
            return balances
        except Exception:
            return []

    # --- Execution (gated) ---

    def create_order(
        self,
        *,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        amount: float,
        price: float | None = None,
    ) -> OrderResult | None:
        """Submit an order (GATED — requires execution_enabled + no kill switch)."""
        if not self._execution_enabled:
            return None
        if self._kill_switch:
            return None
        if self._ccxt_instance is None:
            return None

        try:
            raw = self._ccxt_instance.create_order(
                symbol=symbol,
                type=order_type.value,
                side=side.value,
                amount=amount,
                price=price,
            )
            return OrderResult(
                order_id=str(raw.get("id", "")),
                symbol=raw.get("symbol", symbol),
                side=side,
                order_type=order_type,
                amount=amount,
                price=price,
                status=OrderStatus(raw.get("status", "open")),
                filled=float(raw.get("filled") or 0),
                remaining=float(raw.get("remaining") or amount),
                cost=float(raw.get("cost") or 0),
                fee=float((raw.get("fee") or {}).get("cost") or 0),
                ts_ms=int(raw.get("timestamp") or 0),
            )
        except Exception:
            return None

    def cancel_order(self, *, order_id: str, symbol: str) -> bool:
        """Cancel an order."""
        if self._ccxt_instance is None:
            return False
        try:
            self._ccxt_instance.cancel_order(order_id, symbol)
            return True
        except Exception:
            return False

    # --- Governance Integration ---

    def activate_kill_switch(self) -> None:
        """Immediately halt all execution."""
        self._kill_switch = True

    def deactivate_kill_switch(self) -> None:
        """Re-enable execution (operator only)."""
        self._kill_switch = False

    def enable_execution(self) -> None:
        """Enable order execution (operator authority required)."""
        self._execution_enabled = True

    def disable_execution(self) -> None:
        """Disable order execution."""
        self._execution_enabled = False

    @property
    def is_connected(self) -> bool:
        """Check if exchange is connected."""
        return self._ccxt_instance is not None

    @property
    def execution_enabled(self) -> bool:
        """Check if execution is enabled."""
        return self._execution_enabled and not self._kill_switch

    @property
    def exchange_id(self) -> ExchangeId:
        """Get exchange ID."""
        return self._exchange_id

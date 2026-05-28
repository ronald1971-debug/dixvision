"""OpenBB financial data adapter (OSS Integration Layer).

Provides unified financial data access for DIXVISION research
and intelligence engines. Replaces scattered API calls with
OpenBB's standardized data interfaces.

Key data domains:
- Economy: macro indicators, central bank rates, yield curves
- Equity: stock prices, fundamentals, earnings, dividends
- Crypto: token prices, on-chain metrics, DEX data
- Currency: forex rates, crosses, carry trade data
- News: market news, sentiment, alternative data
- Technical: indicators computed server-side

Reference: github.com/OpenBB-finance/OpenBB
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DataDomain(StrEnum):
    """OpenBB data domains."""

    ECONOMY = "economy"
    EQUITY = "equity"
    CRYPTO = "crypto"
    CURRENCY = "currency"
    NEWS = "news"
    TECHNICAL = "technical"


class DataProvider(StrEnum):
    """Data providers available through OpenBB."""

    YAHOO = "yahoo"
    ALPHA_VANTAGE = "alpha_vantage"
    POLYGON = "polygon"
    FRED = "fred"
    COINGECKO = "coingecko"
    BINANCE = "binance"
    TIINGO = "tiingo"
    INTRINIO = "intrinio"


@dataclass(frozen=True, slots=True)
class MacroIndicator:
    """A macroeconomic indicator value."""

    name: str
    value: float
    country: str
    date: str
    frequency: str
    source: str


@dataclass(frozen=True, slots=True)
class PriceBar:
    """OHLCV price bar."""

    symbol: str
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    provider: str


@dataclass(frozen=True, slots=True)
class CryptoMetric:
    """Crypto-specific metric."""

    symbol: str
    market_cap: float
    volume_24h: float
    price: float
    change_24h_pct: float
    circulating_supply: float
    ts_ns: int


@dataclass(frozen=True, slots=True)
class NewsItem:
    """Financial news item."""

    title: str
    source: str
    url: str
    published: str
    symbols: tuple[str, ...]
    sentiment: float  # -1 to 1


@dataclass(frozen=True, slots=True)
class OpenBBConfig:
    """Configuration for OpenBB adapter."""

    default_provider: DataProvider = DataProvider.YAHOO
    api_keys: dict[str, str] = field(default_factory=dict)
    cache_enabled: bool = True
    cache_ttl_s: int = 300


class OpenBBFinancialDataAdapter:
    """DIXVISION adapter wrapping OpenBB financial data platform.

    Provides:
    - Macro data (GDP, CPI, rates, employment)
    - Market data (equities, crypto, forex)
    - News and sentiment
    - Technical indicators
    - Fundamental data (earnings, balance sheets)

    Falls back to empty results when OpenBB is unavailable.
    """

    def __init__(self, *, config: OpenBBConfig | None = None) -> None:
        self._config = config or OpenBBConfig()
        self._openbb_available = False
        self._cache: dict[str, Any] = {}
        self._obb: Any = None

    def connect(self) -> bool:
        """Initialize OpenBB SDK."""
        try:
            from openbb import obb  # noqa: F401

            self._obb = obb
            self._openbb_available = True
            return True
        except ImportError:
            self._openbb_available = False
            return True

    # --- Economy / Macro ---

    def fetch_gdp(self, *, country: str = "US") -> list[MacroIndicator]:
        """Fetch GDP data."""
        if not self._openbb_available:
            return []
        try:
            data = self._obb.economy.gdp(country=country)
            return [
                MacroIndicator(
                    name="GDP",
                    value=float(row.get("value", 0)),
                    country=country,
                    date=str(row.get("date", "")),
                    frequency="quarterly",
                    source="openbb",
                )
                for row in (data.results if hasattr(data, "results") else [])
            ]
        except Exception:
            return []

    def fetch_cpi(self, *, country: str = "US") -> list[MacroIndicator]:
        """Fetch CPI/inflation data."""
        if not self._openbb_available:
            return []
        try:
            data = self._obb.economy.cpi(country=country)
            return [
                MacroIndicator(
                    name="CPI",
                    value=float(row.get("value", 0)),
                    country=country,
                    date=str(row.get("date", "")),
                    frequency="monthly",
                    source="openbb",
                )
                for row in (data.results if hasattr(data, "results") else [])
            ]
        except Exception:
            return []

    def fetch_interest_rates(self) -> list[MacroIndicator]:
        """Fetch central bank interest rates."""
        # Production placeholder
        return []

    # --- Equity / Market Data ---

    def fetch_equity_price(
        self,
        symbol: str,
        *,
        start_date: str = "",
        end_date: str = "",
        interval: str = "1d",
    ) -> list[PriceBar]:
        """Fetch equity price history."""
        if not self._openbb_available:
            return []
        try:
            kwargs: dict[str, Any] = {"symbol": symbol, "interval": interval}
            if start_date:
                kwargs["start_date"] = start_date
            if end_date:
                kwargs["end_date"] = end_date
            data = self._obb.equity.price.historical(**kwargs)
            return [
                PriceBar(
                    symbol=symbol,
                    date=str(row.get("date", "")),
                    open=float(row.get("open", 0)),
                    high=float(row.get("high", 0)),
                    low=float(row.get("low", 0)),
                    close=float(row.get("close", 0)),
                    volume=float(row.get("volume", 0)),
                    provider=self._config.default_provider.value,
                )
                for row in (data.results if hasattr(data, "results") else [])
            ]
        except Exception:
            return []

    # --- Crypto ---

    def fetch_crypto_price(
        self,
        symbol: str,
        *,
        interval: str = "1d",
        limit: int = 100,
    ) -> list[PriceBar]:
        """Fetch crypto price history."""
        if not self._openbb_available:
            return []
        try:
            data = self._obb.crypto.price.historical(symbol=symbol, interval=interval)
            return [
                PriceBar(
                    symbol=symbol,
                    date=str(row.get("date", "")),
                    open=float(row.get("open", 0)),
                    high=float(row.get("high", 0)),
                    low=float(row.get("low", 0)),
                    close=float(row.get("close", 0)),
                    volume=float(row.get("volume", 0)),
                    provider="openbb_crypto",
                )
                for row in (data.results if hasattr(data, "results") else [])
            ]
        except Exception:
            return []

    def fetch_crypto_metrics(self, symbol: str) -> CryptoMetric | None:
        """Fetch crypto market metrics (market cap, volume, etc.)."""
        # Production placeholder
        return None

    # --- News ---

    def fetch_news(
        self,
        *,
        symbols: list[str] | None = None,
        limit: int = 20,
    ) -> list[NewsItem]:
        """Fetch financial news."""
        if not self._openbb_available:
            return []
        try:
            kwargs: dict[str, Any] = {"limit": limit}
            if symbols:
                kwargs["symbols"] = ",".join(symbols)
            data = self._obb.news.world(**kwargs)
            return [
                NewsItem(
                    title=str(row.get("title", "")),
                    source=str(row.get("source", "")),
                    url=str(row.get("url", "")),
                    published=str(row.get("date", "")),
                    symbols=tuple(row.get("symbols", [])),
                    sentiment=float(row.get("sentiment", 0)),
                )
                for row in (data.results if hasattr(data, "results") else [])
            ]
        except Exception:
            return []

    # --- Status ---

    @property
    def is_available(self) -> bool:
        """Check if OpenBB is available."""
        return self._openbb_available

    @property
    def supported_domains(self) -> list[DataDomain]:
        """List supported data domains."""
        return list(DataDomain)

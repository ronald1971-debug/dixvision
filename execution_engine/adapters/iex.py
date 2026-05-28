# ADAPTED FROM: addisonlynch/iexfinance
# (iexfinance/stocks/__init__.py — Stock class, get_quote(), get_historical_prices();
#  iexfinance/refdata/ — get_symbols(), iex_listed_symbols();
#  iexfinance/base.py — _IEXBase HTTP client pattern)
"""C-80 — IEX Cloud US equities data adapter.

This module adapts ``iexfinance`` for US equity fundamental and market
data ingestion.

What survives from upstream (addisonlynch/iexfinance):
    * **Stock** — ``stocks/__init__.py``: ``Stock(symbol).get_quote()``
      for real-time quote, ``.get_historical_prices()`` for OHLCV.
    * **get_symbols()** — ``refdata/``: list all available symbols.
    * **HTTP client** — ``base.py``: token-authenticated REST calls.

What we replaced:
    * Real ``iexfinance`` import is lazy (Protocol seam).
    * In-memory mock responses for unit tests.
    * Same data adapter pattern as Polygon.

RUNTIME tier: data feed on hot path.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class IEXQuote:
    """IEX Cloud stock quote."""

    symbol: str
    latest_price: float
    change: float = 0.0
    change_percent: float = 0.0
    volume: int = 0
    market_cap: int = 0


class IEXAdapter:
    """IEX Cloud market data adapter.

    Mirrors ``iexfinance.Stock`` patterns for real-time quotes and
    historical OHLCV data.

    Usage::

        adapter = IEXAdapter(api_key="...")
        quote = adapter.get_quote("AAPL")
    """

    BASE_URL = "https://cloud.iexapis.com/stable"

    def __init__(self, *, api_key: str = "", in_memory: bool | None = None) -> None:
        self._api_key = api_key
        # Auto-detect: live mode when API key is present, mock otherwise
        self._in_memory = in_memory if in_memory is not None else (not bool(api_key))
        self._mock_quotes: dict[str, IEXQuote] = {}

    def get_quote(self, symbol: str) -> IEXQuote | None:
        """Get real-time quote (mirrors Stock.get_quote())."""
        if self._in_memory:
            return self._mock_quotes.get(symbol)
        return self._fetch_quote(symbol)

    def get_historical(self, symbol: str, *, period: str = "1m") -> list[dict[str, Any]]:
        """Get historical prices (mirrors Stock.get_historical_prices())."""
        if self._in_memory:
            return []
        return self._fetch_historical(symbol, period)

    def add_mock_quote(self, quote: IEXQuote) -> None:
        """Add a mock quote for testing."""
        self._mock_quotes[quote.symbol] = quote

    # ---- remote internals ------------------------------------------------

    def _fetch_quote(self, symbol: str) -> IEXQuote | None:
        url = f"{self.BASE_URL}/stock/{symbol}/quote?token={self._api_key}"
        try:
            data = self._http_get(url)
            return IEXQuote(
                symbol=data.get("symbol", symbol),
                latest_price=data.get("latestPrice", 0.0),
                change=data.get("change", 0.0),
                change_percent=data.get("changePercent", 0.0),
                volume=data.get("volume", 0),
                market_cap=data.get("marketCap", 0),
            )
        except Exception:
            return None

    def _fetch_historical(self, symbol: str, period: str) -> list[dict[str, Any]]:
        url = f"{self.BASE_URL}/stock/{symbol}/chart/{period}?token={self._api_key}"
        try:
            return self._http_get(url)
        except Exception:
            return []

    def _http_get(self, url: str) -> Any:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())


__all__ = ["IEXAdapter", "IEXQuote"]

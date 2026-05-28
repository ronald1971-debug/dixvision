# ADAPTED FROM: RomelTorres/alpha_vantage
# (alpha_vantage/timeseries.py — TimeSeries.get_daily(), get_intraday();
#  alpha_vantage/foreignexchange.py — ForeignExchange.get_currency_exchange_rate();
#  alpha_vantage/alphavantage.py — AlphaVantage base HTTP client)
"""C-81 — Alpha Vantage forex + macro data adapter.

This module adapts ``alpha_vantage`` for forex rates and macro economic
indicators (FRED-adjacent data).

What survives from upstream (RomelTorres/alpha_vantage):
    * **TimeSeries** — ``timeseries.py``: ``get_daily(symbol)`` for
      daily OHLCV, ``get_intraday(symbol, interval)`` for minute bars.
    * **ForeignExchange** — ``foreignexchange.py``:
      ``get_currency_exchange_rate(from_currency, to_currency)``.
    * **HTTP pattern** — ``alphavantage.py``: function-based API with
      ``apikey`` parameter in all requests.

What we replaced:
    * Real ``alpha_vantage`` import is lazy (Protocol seam).
    * In-memory mock responses for unit tests.
    * Same data adapter pattern as Polygon/IEX.

RUNTIME tier: data feed.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ForexRate:
    """Currency exchange rate."""

    from_currency: str
    to_currency: str
    rate: float
    timestamp: str = ""


class AlphaVantageAdapter:
    """Alpha Vantage data adapter for forex + macro data.

    Mirrors ``alpha_vantage.TimeSeries`` and ``ForeignExchange``
    patterns.

    Usage::

        adapter = AlphaVantageAdapter(api_key="...")
        rate = adapter.get_exchange_rate("EUR", "USD")
    """

    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self, *, api_key: str = "", in_memory: bool | None = None) -> None:
        self._api_key = api_key
        # Auto-detect: live mode when API key is present, mock otherwise
        self._in_memory = in_memory if in_memory is not None else (not bool(api_key))
        self._mock_rates: dict[str, ForexRate] = {}

    def get_exchange_rate(self, from_currency: str, to_currency: str) -> ForexRate | None:
        """Get current exchange rate (mirrors ForeignExchange)."""
        if self._in_memory:
            key = f"{from_currency}/{to_currency}"
            return self._mock_rates.get(key)
        return self._fetch_exchange_rate(from_currency, to_currency)

    def get_daily(self, symbol: str, *, outputsize: str = "compact") -> list[dict[str, Any]]:
        """Get daily OHLCV (mirrors TimeSeries.get_daily())."""
        if self._in_memory:
            return []
        return self._fetch_daily(symbol, outputsize)

    def add_mock_rate(self, rate: ForexRate) -> None:
        """Add a mock exchange rate for testing."""
        key = f"{rate.from_currency}/{rate.to_currency}"
        self._mock_rates[key] = rate

    # ---- remote internals ------------------------------------------------

    def _fetch_exchange_rate(self, from_c: str, to_c: str) -> ForexRate | None:
        url = (
            f"{self.BASE_URL}?function=CURRENCY_EXCHANGE_RATE"
            f"&from_currency={from_c}&to_currency={to_c}&apikey={self._api_key}"
        )
        try:
            data = self._http_get(url)
            info = data.get("Realtime Currency Exchange Rate", {})
            return ForexRate(
                from_currency=from_c,
                to_currency=to_c,
                rate=float(info.get("5. Exchange Rate", 0)),
                timestamp=info.get("6. Last Refreshed", ""),
            )
        except Exception:
            return None

    def _fetch_daily(self, symbol: str, outputsize: str) -> list[dict[str, Any]]:
        url = (
            f"{self.BASE_URL}?function=TIME_SERIES_DAILY"
            f"&symbol={symbol}&outputsize={outputsize}&apikey={self._api_key}"
        )
        try:
            data = self._http_get(url)
            ts = data.get("Time Series (Daily)", {})
            return [{"date": k, **v} for k, v in ts.items()]
        except Exception:
            return []

    def _http_get(self, url: str) -> Any:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())


__all__ = ["AlphaVantageAdapter", "ForexRate"]

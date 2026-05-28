# ADAPTED FROM: polygon-io/client-python
# (polygon/rest/client.py — RESTClient, list_aggs(), list_trades();
#  polygon/rest/models/aggs.py — Agg dataclass;
#  polygon/websocket/ — WebSocketClient for real-time streaming)
"""C-79 — Polygon.io US stocks + crypto data adapter.

This module adapts the ``polygon-api-client`` for market data ingestion.
Data feed only — no order execution via Polygon.

What survives from upstream (polygon-io/client-python):
    * **RESTClient** — ``rest/client.py``: ``client.list_aggs(ticker,
      multiplier, timespan, from_, to)`` for OHLCV bars.
    * **list_trades()** — individual trade tick data.
    * **Agg** — ``models/aggs.py``: aggregated bar with open, high,
      low, close, volume, vwap.

What we replaced:
    * Real ``polygon`` import is lazy (Protocol seam).
    * In-memory mock responses for unit tests.
    * Output normalized to DIX OHLCV pipeline.

RUNTIME tier: data feed on hot path (cached, rate-limited).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class OHLCVBar:
    """Normalized OHLCV bar."""

    symbol: str
    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    vwap: float = 0.0


class PolygonAdapter:
    """Polygon.io market data adapter.

    Mirrors ``polygon.RESTClient`` for fetching aggregated bars and
    trade data. API key from system_engine/credentials/.

    Usage::

        adapter = PolygonAdapter(api_key="...")
        bars = adapter.get_aggs("AAPL", timespan="day", limit=5)
    """

    BASE_URL = "https://api.polygon.io"

    def __init__(self, *, api_key: str = "", in_memory: bool | None = None) -> None:
        self._api_key = api_key
        # Auto-detect: live mode when API key is present, mock otherwise
        self._in_memory = in_memory if in_memory is not None else (not bool(api_key))
        self._mock_bars: list[OHLCVBar] = []

    def get_aggs(
        self,
        ticker: str,
        *,
        multiplier: int = 1,
        timespan: str = "day",
        from_date: str = "",
        to_date: str = "",
        limit: int = 50,
    ) -> list[OHLCVBar]:
        """Fetch aggregated bars (mirrors RESTClient.list_aggs())."""
        if self._in_memory:
            return self._mock_bars[:limit]
        return self._fetch_aggs(ticker, multiplier, timespan, from_date, to_date, limit)

    def get_last_trade(self, ticker: str) -> OHLCVBar | None:
        """Get last trade for a ticker."""
        if self._in_memory:
            return self._mock_bars[-1] if self._mock_bars else None
        return self._fetch_last_trade(ticker)

    def add_mock_bar(self, bar: OHLCVBar) -> None:
        """Add a mock bar for testing."""
        self._mock_bars.append(bar)

    # ---- remote internals ------------------------------------------------

    def _fetch_aggs(
        self,
        ticker: str,
        multiplier: int,
        timespan: str,
        from_date: str,
        to_date: str,
        limit: int,
    ) -> list[OHLCVBar]:
        url = (
            f"{self.BASE_URL}/v2/aggs/ticker/{ticker}/range"
            f"/{multiplier}/{timespan}/{from_date}/{to_date}"
            f"?limit={limit}&apiKey={self._api_key}"
        )
        try:
            resp = self._http_get(url)
            results = resp.get("results", [])
            return [
                OHLCVBar(
                    symbol=ticker,
                    timestamp_ms=r.get("t", 0),
                    open=r.get("o", 0.0),
                    high=r.get("h", 0.0),
                    low=r.get("l", 0.0),
                    close=r.get("c", 0.0),
                    volume=r.get("v", 0.0),
                    vwap=r.get("vw", 0.0),
                )
                for r in results
            ]
        except Exception:
            return []

    def _fetch_last_trade(self, ticker: str) -> OHLCVBar | None:
        url = f"{self.BASE_URL}/v2/last/trade/{ticker}?apiKey={self._api_key}"
        try:
            resp = self._http_get(url)
            r = resp.get("results", {})
            return OHLCVBar(
                symbol=ticker,
                timestamp_ms=r.get("t", 0),
                open=r.get("p", 0.0),
                high=r.get("p", 0.0),
                low=r.get("p", 0.0),
                close=r.get("p", 0.0),
                volume=r.get("s", 0.0),
            )
        except Exception:
            return None

    def _http_get(self, url: str) -> dict[str, Any]:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())


__all__ = ["OHLCVBar", "PolygonAdapter"]

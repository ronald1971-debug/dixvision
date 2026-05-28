"""TradingView ideas adapter (BUILD-DIRECTIVE §12).

Read-only adapter for ingesting trading ideas from TradingView's
public idea feed. No API key required — uses TradingView's public
widget/recommendation endpoints.

__capability_tier__ = 0  (read-only ingestion)
"""

from __future__ import annotations

from system import time_source

__capability_tier__ = 0
__forbidden_tiers__ = (5,)

import json
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TradingViewIdea:
    """A trading idea from TradingView."""

    idea_id: str
    author: str
    symbol: str
    direction: str  # "long" | "short" | "neutral"
    timeframe: str
    description: str
    likes: int
    comments: int
    author_reputation: float  # 0-1 based on TV reputation
    chart_patterns: tuple[str, ...]
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    ts_ns: int = 0
    source_platform: str = "tradingview"


class TradingViewIdeasAdapter:
    """Read-only adapter for TradingView public data.

    Uses TradingView's public scan/recommendation API — no auth required.
    Fetches technical analysis recommendations and symbol overviews.
    """

    _SCAN_URL = "https://scanner.tradingview.com/crypto/scan"
    _USER_AGENT = "DIX-VISION/42.2 (market-data)"

    def __init__(self, *, api_base_url: str = "") -> None:
        self._api_base_url = api_base_url or self._SCAN_URL

    def fetch_signals(
        self,
        *,
        symbol: str | None = None,
        min_likes: int = 10,
        limit: int = 50,
    ) -> list[TradingViewIdea]:
        """Fetch TradingView scanner data as trading signals."""
        now_ns = time_source.wall_ns()
        symbols = [symbol] if symbol else ["BTCUSD", "ETHUSD", "SOLUSD"]
        ideas: list[TradingViewIdea] = []

        for sym in symbols:
            try:
                rec = self._fetch_recommendation(sym)
                if rec:
                    direction = (
                        "long"
                        if rec.get("RECOMMENDATION") == "BUY"
                        else ("short" if rec.get("RECOMMENDATION") == "SELL" else "neutral")
                    )
                    ideas.append(
                        TradingViewIdea(
                            idea_id=f"tv-{sym}-{now_ns}",
                            author="TradingView Scanner",
                            symbol=sym,
                            direction=direction,
                            timeframe="1D",
                            description=f"Technical: {rec.get('RECOMMENDATION', 'NEUTRAL')}",
                            likes=0,
                            comments=0,
                            author_reputation=0.8,
                            chart_patterns=tuple(
                                k for k, v in rec.items() if k.startswith("pattern_") and v != 0
                            ),
                            ts_ns=now_ns,
                        )
                    )
            except Exception:
                continue

        return ideas[:limit]

    def _fetch_recommendation(self, symbol: str) -> dict[str, Any] | None:
        """Fetch technical analysis recommendation from TradingView scanner."""
        payload = json.dumps(
            {
                "symbols": {"tickers": [f"CRYPTO:{symbol}"]},
                "columns": [
                    "Recommend.All",
                    "Recommend.MA",
                    "Recommend.Other",
                    "RSI",
                    "RSI[1]",
                    "Stoch.K",
                    "Stoch.D",
                    "MACD.macd",
                    "MACD.signal",
                    "ADX",
                    "AO",
                    "close",
                    "volume",
                    "change",
                ],
            }
        ).encode()
        try:
            req = urllib.request.Request(
                self._api_base_url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": self._USER_AGENT,
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())

            rows = data.get("data", [])
            if not rows:
                return None

            values = rows[0].get("d", [])
            columns = [
                "Recommend.All",
                "Recommend.MA",
                "Recommend.Other",
                "RSI",
                "RSI[1]",
                "Stoch.K",
                "Stoch.D",
                "MACD.macd",
                "MACD.signal",
                "ADX",
                "AO",
                "close",
                "volume",
                "change",
            ]
            result = dict(zip(columns, values, strict=False))

            rec_all = result.get("Recommend.All", 0) or 0
            if rec_all >= 0.5:
                result["RECOMMENDATION"] = "STRONG_BUY"
            elif rec_all >= 0.1:
                result["RECOMMENDATION"] = "BUY"
            elif rec_all <= -0.5:
                result["RECOMMENDATION"] = "STRONG_SELL"
            elif rec_all <= -0.1:
                result["RECOMMENDATION"] = "SELL"
            else:
                result["RECOMMENDATION"] = "NEUTRAL"
            return result
        except Exception:
            return None

    def fetch_market_data(
        self,
        *,
        symbol: str,
        window_hours: int = 24,
    ) -> dict[str, Any]:
        """Fetch aggregated idea sentiment for a symbol."""
        rec = self._fetch_recommendation(symbol)
        if rec:
            rec_val = rec.get("Recommend.All", 0) or 0
            long_ratio = max(0.0, min(1.0, 0.5 + rec_val / 2))
        else:
            rec_val = 0
            long_ratio = 0.5
        return {
            "symbol": symbol,
            "window_hours": window_hours,
            "recommendation": rec.get("RECOMMENDATION", "NEUTRAL") if rec else "NEUTRAL",
            "recommend_value": rec_val,
            "long_ratio": long_ratio,
            "short_ratio": 1.0 - long_ratio,
            "rsi": rec.get("RSI") if rec else None,
            "macd": rec.get("MACD.macd") if rec else None,
            "source_platform": "tradingview",
        }

    def fetch_strategy_results(
        self,
        *,
        author: str | None = None,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch historical scanner accuracy for a symbol."""
        if not symbol:
            return []
        rec = self._fetch_recommendation(symbol)
        if not rec:
            return []
        return [
            {
                "symbol": symbol,
                "recommendation": rec.get("RECOMMENDATION"),
                "rsi": rec.get("RSI"),
                "adx": rec.get("ADX"),
                "volume": rec.get("volume"),
                "source": "tradingview_scanner",
            }
        ]

    def fetch_top_authors(
        self,
        *,
        symbol: str | None = None,
        min_reputation: float = 0.7,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """TradingView scanner does not expose author data."""
        return []

    def fetch_chart_patterns(
        self,
        *,
        symbol: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Derive chart pattern signals from scanner indicators."""
        rec = self._fetch_recommendation(symbol)
        if not rec:
            return []
        patterns: list[dict[str, Any]] = []
        rsi = rec.get("RSI")
        if rsi is not None:
            if rsi > 70:
                patterns.append({"pattern": "overbought", "indicator": "RSI", "value": rsi})
            elif rsi < 30:
                patterns.append({"pattern": "oversold", "indicator": "RSI", "value": rsi})
        ao = rec.get("AO")
        if ao is not None and ao != 0:
            patterns.append(
                {
                    "pattern": "bullish_momentum" if ao > 0 else "bearish_momentum",
                    "indicator": "AO",
                    "value": ao,
                }
            )
        return patterns[:limit]

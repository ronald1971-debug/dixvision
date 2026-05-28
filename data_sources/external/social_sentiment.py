"""Social sentiment adapter (BUILD-DIRECTIVE §14).

Fetches sentiment data from X/Twitter, Reddit, Telegram.
B-FETCH enforced: only fetch_* methods permitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SocialSentimentObservation:
    """Canonical social sentiment observation."""

    platform_source: str
    symbol: str
    sentiment_score: float
    volume: int
    velocity: float
    ts_ns: int


class SocialSentimentAdapter:
    """Read-only adapter for social media sentiment data."""

    platform: str = "social_sentiment"

    def fetch_sentiment(
        self,
        *,
        raw_data: list[dict[str, Any]],
        source: str,
    ) -> list[SocialSentimentObservation]:
        """Fetch social sentiment for symbols."""
        return [
            SocialSentimentObservation(
                platform_source=source,
                symbol=str(d.get("symbol", "")),
                sentiment_score=float(d.get("sentiment", 0.0)),
                volume=int(d.get("volume", 0)),
                velocity=float(d.get("velocity", 0.0)),
                ts_ns=int(d.get("ts_ns", 0)),
            )
            for d in raw_data
        ]

    def fetch_trending(self, *, trending_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Fetch trending symbols from social platforms."""
        return [
            {
                "platform": self.platform,
                "symbol": t.get("symbol", ""),
                "mentions_24h": int(t.get("mentions_24h", 0)),
                "sentiment_delta": float(t.get("sentiment_delta", 0.0)),
            }
            for t in trending_data
        ]

"""News feed adapter — reference template (BUILD-DIRECTIVE §14).

Demonstrates the canonical pattern for external data source adapters.
This adapter fetches from news APIs (Bloomberg, Reuters, CoinDesk, etc.)
and normalizes into the canonical news observation format.

All external data source adapters follow this pattern:
1. Only fetch_* public methods (B-FETCH enforced)
2. Returns normalized dataclass observations
3. No state mutation, no side effects
4. Platform-specific parsing in private methods
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class NewsObservation:
    """Canonical news observation from any external news source."""

    source: str
    headline: str
    summary: str
    symbols: tuple[str, ...]
    sentiment_score: float
    relevance_score: float
    published_ts_ns: int
    ingested_ts_ns: int
    url: str = ""
    language: str = "en"


class NewsFeedAdapter:
    """Read-only news data adapter (reference template).

    Ingests from configured news sources and normalizes into
    NewsObservation records for the intelligence pipeline.
    """

    platform: str = "news_feed"

    def fetch_headlines(
        self, *, raw_articles: list[dict[str, Any]], source: str
    ) -> list[NewsObservation]:
        """Fetch and normalize news headlines from a source."""
        return [
            NewsObservation(
                source=source,
                headline=str(a.get("title", "")),
                summary=str(a.get("description", "")),
                symbols=tuple(a.get("symbols", [])),
                sentiment_score=float(a.get("sentiment", 0.0)),
                relevance_score=float(a.get("relevance", 0.5)),
                published_ts_ns=int(a.get("published_ts_ns", 0)),
                ingested_ts_ns=int(a.get("ingested_ts_ns", 0)),
                url=str(a.get("url", "")),
                language=str(a.get("language", "en")),
            )
            for a in raw_articles
        ]

    def fetch_market_sentiment(
        self, *, sentiment_data: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Fetch aggregated market sentiment scores."""
        return [
            {
                "platform": self.platform,
                "symbol": s.get("symbol", ""),
                "sentiment": float(s.get("sentiment", 0.0)),
                "volume": int(s.get("mentions", 0)),
                "source": s.get("source", ""),
            }
            for s in sentiment_data
        ]

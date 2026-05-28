"""X (Twitter) crypto sentiment adapter (BUILD-DIRECTIVE §12).

Read-only adapter for ingesting crypto sentiment signals from X/Twitter.
Fetches tweets via X API v2 when bearer token is available, otherwise
returns empty (graceful degradation).

__capability_tier__ = 0  (read-only ingestion)

All output goes through the canonical normalizer before reaching engines.
"""

from __future__ import annotations

from system import time_source

__capability_tier__ = 0
__forbidden_tiers__ = (5,)

import json
import os
import re
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class XSentimentSignal:
    """A sentiment signal extracted from X/Twitter."""

    tweet_id: str
    author_handle: str
    author_followers: int
    content: str
    mentioned_tickers: tuple[str, ...]
    sentiment_score: float  # -1=bearish, +1=bullish
    engagement_score: float  # normalized 0-1
    ts_ns: int
    is_thread: bool = False
    source_platform: str = "x"


_TICKER_PATTERN = re.compile(
    r"\$?(BTC|ETH|SOL|ADA|DOT|AVAX|MATIC|LINK|UNI|AAVE|"
    r"DOGE|SHIB|XRP|BNB|LTC|ATOM|NEAR|ARB|OP|APT)\b",
    re.IGNORECASE,
)

_BULLISH = frozenset(
    {
        "bullish",
        "moon",
        "pump",
        "buy",
        "long",
        "breakout",
        "rocket",
        "ath",
        "rally",
        "accumulate",
        "undervalued",
        "green",
        "gains",
        "hodl",
        "diamond",
    }
)
_BEARISH = frozenset(
    {
        "bearish",
        "dump",
        "sell",
        "short",
        "crash",
        "rug",
        "scam",
        "overvalued",
        "red",
        "loss",
        "paper",
        "dead",
        "ponzi",
        "bubble",
    }
)


def _score_sentiment(text: str) -> float:
    words = set(text.lower().split())
    bull = len(words & _BULLISH)
    bear = len(words & _BEARISH)
    total = bull + bear
    if total == 0:
        return 0.0
    return (bull - bear) / total


class XCryptoSentimentAdapter:
    """Read-only adapter for X crypto sentiment.

    Uses X API v2 recent search when TWITTER_BEARER_TOKEN is set.
    Gracefully returns empty when no credentials are available.
    """

    _API_URL = "https://api.twitter.com/2/tweets/search/recent"

    def __init__(self, *, api_base_url: str = "") -> None:
        self._api_base_url = api_base_url or self._API_URL
        self._bearer_token = os.environ.get("TWITTER_BEARER_TOKEN", "")

    def fetch_signals(
        self,
        *,
        keywords: list[str] | None = None,
        handles: list[str] | None = None,
        min_followers: int = 1000,
        limit: int = 100,
    ) -> list[XSentimentSignal]:
        """Fetch sentiment signals from X API v2."""
        if not self._bearer_token:
            return []

        query_parts = keywords or ["crypto", "BTC", "ETH", "SOL"]
        query = " OR ".join(query_parts) + " -is:retweet lang:en"
        now_ns = time_source.wall_ns()
        signals: list[XSentimentSignal] = []

        try:
            url = (
                f"{self._api_base_url}?query={urllib.request.quote(query)}"
                f"&max_results={min(limit, 100)}"
                f"&tweet.fields=public_metrics,author_id,created_at"
            )
            req = urllib.request.Request(url)
            req.add_header("Authorization", f"Bearer {self._bearer_token}")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())

            for tweet in data.get("data", []):
                text = tweet.get("text", "")
                tickers = tuple(
                    sorted(set(m.group(1).upper() for m in _TICKER_PATTERN.finditer(text)))
                )
                if not tickers:
                    continue

                metrics = tweet.get("public_metrics", {})
                likes = metrics.get("like_count", 0)
                retweets = metrics.get("retweet_count", 0)
                replies = metrics.get("reply_count", 0)
                engagement = min(1.0, (likes + retweets * 2 + replies) / 1000)

                signals.append(
                    XSentimentSignal(
                        tweet_id=tweet.get("id", ""),
                        author_handle=tweet.get("author_id", ""),
                        author_followers=0,
                        content=text[:280],
                        mentioned_tickers=tickers,
                        sentiment_score=_score_sentiment(text),
                        engagement_score=engagement,
                        ts_ns=now_ns,
                    )
                )
        except Exception:
            pass

        return signals[:limit]

    def fetch_market_data(
        self,
        *,
        ticker: str,
        window_hours: int = 24,
    ) -> dict[str, Any]:
        """Fetch aggregated sentiment data for a ticker."""
        signals = self.fetch_signals(keywords=[f"${ticker}", ticker], limit=50)
        matching = [s for s in signals if ticker.upper() in s.mentioned_tickers]
        avg_sentiment = (
            sum(s.sentiment_score for s in matching) / len(matching) if matching else 0.0
        )
        return {
            "ticker": ticker,
            "window_hours": window_hours,
            "tweet_count": len(matching),
            "avg_sentiment": avg_sentiment,
            "top_authors": [s.author_handle for s in matching[:5]],
            "source_platform": "x",
        }

    def fetch_trending_topics(self, *, limit: int = 20) -> list[dict[str, Any]]:
        """Fetch currently trending crypto topics on X."""
        signals = self.fetch_signals(limit=50)
        ticker_counts: dict[str, int] = {}
        for s in signals:
            for t in s.mentioned_tickers:
                ticker_counts[t] = ticker_counts.get(t, 0) + 1
        sorted_tickers = sorted(ticker_counts.items(), key=lambda x: -x[1])
        return [{"ticker": t, "mention_count": c, "source": "x"} for t, c in sorted_tickers[:limit]]

    def fetch_influencer_activity(
        self,
        *,
        handles: list[str],
    ) -> list[dict[str, Any]]:
        """Fetch recent activity from known crypto influencers."""
        if not self._bearer_token:
            return []
        results: list[dict[str, Any]] = []
        for handle in handles[:5]:
            signals = self.fetch_signals(keywords=[f"from:{handle}"], limit=10)
            if signals:
                results.append(
                    {
                        "handle": handle,
                        "recent_tweets": len(signals),
                        "avg_sentiment": sum(s.sentiment_score for s in signals) / len(signals),
                    }
                )
        return results

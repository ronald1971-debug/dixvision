"""Reddit sentiment adapter (BUILD-DIRECTIVE §12).

Read-only adapter for ingesting sentiment from crypto/finance subreddits.
Monitors r/cryptocurrency, r/wallstreetbets, r/bitcoin, r/solana, etc.

Uses Reddit's public JSON API (append .json to any subreddit URL) —
no authentication required for read-only access.

__capability_tier__ = 0  (read-only ingestion)

All output goes through the canonical normalizer.
"""

from __future__ import annotations

from system import time_source

__capability_tier__ = 0
__forbidden_tiers__ = (5,)

import json
import re
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RedditSignal:
    """A sentiment signal extracted from Reddit."""

    post_id: str
    subreddit: str
    title: str
    author: str
    upvotes: int
    comment_count: int
    mentioned_tickers: tuple[str, ...]
    sentiment_score: float  # -1=bearish, +1=bullish
    hype_score: float  # 0=calm, 1=maximum hype
    ts_ns: int
    source_platform: str = "reddit"


# Common crypto tickers to scan for
_TICKER_PATTERN = re.compile(
    r"\b(BTC|ETH|SOL|ADA|DOT|AVAX|MATIC|LINK|UNI|AAVE|"
    r"DOGE|SHIB|XRP|BNB|LTC|ATOM|NEAR|ARB|OP|APT)\b",
    re.IGNORECASE,
)

# Simple keyword-based sentiment scoring
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
        "diamond hands",
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
        "paper hands",
        "dead",
        "ponzi",
        "bubble",
    }
)


def _score_sentiment(text: str) -> float:
    """Simple keyword-based sentiment scorer (-1 to +1)."""
    words = set(text.lower().split())
    bull = len(words & _BULLISH)
    bear = len(words & _BEARISH)
    total = bull + bear
    if total == 0:
        return 0.0
    return (bull - bear) / total


def _extract_tickers(text: str) -> tuple[str, ...]:
    """Extract mentioned crypto tickers from text."""
    return tuple(sorted(set(m.group(0).upper() for m in _TICKER_PATTERN.finditer(text))))


class RedditSentimentAdapter:
    """Read-only adapter for Reddit finance/crypto sentiment.

    Uses Reddit's public JSON API — no API keys required.
    Append .json to any subreddit listing URL.

    Monitors subreddits for:
    - Ticker mentions and sentiment
    - Hype detection (unusual activity spikes)
    - Narrative formation (emerging themes)
    - Crowd psychology signals
    """

    DEFAULT_SUBREDDITS = (
        "cryptocurrency",
        "bitcoin",
        "ethereum",
        "solana",
        "wallstreetbets",
        "stocks",
        "options",
        "defi",
        "cryptomoonshots",
        "satoshistreetbets",
    )

    _USER_AGENT = "DIX-VISION/42.2 (read-only sentiment monitor)"

    def __init__(
        self,
        *,
        subreddits: list[str] | None = None,
        api_base_url: str = "",
    ) -> None:
        self._subreddits = subreddits or list(self.DEFAULT_SUBREDDITS)
        self._api_base_url = api_base_url or "https://www.reddit.com"

    def fetch_signals(
        self,
        *,
        subreddit: str | None = None,
        limit: int = 100,
    ) -> list[RedditSignal]:
        """Fetch sentiment signals from Reddit's public JSON API."""
        subs = [subreddit] if subreddit else self._subreddits[:3]
        signals: list[RedditSignal] = []
        now_ns = time_source.wall_ns()

        for sub in subs:
            try:
                url = f"{self._api_base_url}/r/{sub}/hot.json?limit={min(limit, 25)}"
                req = urllib.request.Request(url)
                req.add_header("User-Agent", self._USER_AGENT)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read())

                for child in data.get("data", {}).get("children", []):
                    post = child.get("data", {})
                    title = post.get("title", "")
                    selftext = post.get("selftext", "")
                    full_text = f"{title} {selftext}"
                    tickers = _extract_tickers(full_text)
                    if not tickers:
                        continue

                    upvotes = post.get("ups", 0)
                    comments = post.get("num_comments", 0)
                    hype = min(1.0, (upvotes + comments * 2) / 5000)

                    signals.append(
                        RedditSignal(
                            post_id=post.get("id", ""),
                            subreddit=sub,
                            title=title[:200],
                            author=post.get("author", ""),
                            upvotes=upvotes,
                            comment_count=comments,
                            mentioned_tickers=tickers,
                            sentiment_score=_score_sentiment(full_text),
                            hype_score=hype,
                            ts_ns=now_ns,
                        )
                    )
            except Exception:
                continue

        return signals[:limit]

    def fetch_market_data(
        self,
        *,
        ticker: str,
        window_hours: int = 24,
    ) -> dict[str, Any]:
        """Fetch aggregated Reddit sentiment for a ticker."""
        signals = self.fetch_signals(limit=50)
        matching = [s for s in signals if ticker.upper() in s.mentioned_tickers]
        avg_sentiment = (
            sum(s.sentiment_score for s in matching) / len(matching) if matching else 0.0
        )
        return {
            "ticker": ticker,
            "window_hours": window_hours,
            "mention_count": len(matching),
            "avg_sentiment": avg_sentiment,
            "top_posts": [s.title for s in matching[:5]],
            "source_platform": "reddit",
        }

    def fetch_hype_spikes(self, *, threshold: float = 2.0) -> list[dict[str, Any]]:
        """Detect unusual activity spikes (potential pump signals)."""
        signals = self.fetch_signals(limit=50)
        return [
            {
                "ticker": t,
                "hype_score": s.hype_score,
                "subreddit": s.subreddit,
                "title": s.title,
            }
            for s in signals
            if s.hype_score >= threshold / 5.0
            for t in s.mentioned_tickers
        ]

    def fetch_emerging_narratives(self, *, limit: int = 10) -> list[dict[str, Any]]:
        """Detect emerging narrative themes across subreddits."""
        signals = self.fetch_signals(limit=50)
        ticker_counts: dict[str, int] = {}
        for s in signals:
            for t in s.mentioned_tickers:
                ticker_counts[t] = ticker_counts.get(t, 0) + 1
        sorted_tickers = sorted(ticker_counts.items(), key=lambda x: -x[1])
        return [
            {"ticker": t, "mention_count": c, "source": "reddit"} for t, c in sorted_tickers[:limit]
        ]

    def fetch_crowd_sentiment_index(self) -> dict[str, float]:
        """Aggregate crowd sentiment index per asset class."""
        signals = self.fetch_signals(limit=50)
        buckets: dict[str, list[float]] = {
            "crypto_overall": [],
            "btc": [],
            "eth": [],
            "alts": [],
            "defi": [],
            "meme": [],
        }
        defi_tokens = {"UNI", "AAVE", "LINK", "ATOM"}
        meme_tokens = {"DOGE", "SHIB"}
        for s in signals:
            buckets["crypto_overall"].append(s.sentiment_score)
            for t in s.mentioned_tickers:
                if t == "BTC":
                    buckets["btc"].append(s.sentiment_score)
                elif t == "ETH":
                    buckets["eth"].append(s.sentiment_score)
                elif t in defi_tokens:
                    buckets["defi"].append(s.sentiment_score)
                elif t in meme_tokens:
                    buckets["meme"].append(s.sentiment_score)
                else:
                    buckets["alts"].append(s.sentiment_score)
        return {k: (sum(v) / len(v) if v else 0.0) for k, v in buckets.items()}

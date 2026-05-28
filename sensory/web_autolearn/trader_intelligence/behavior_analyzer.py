"""TI-ING-03 — trader behavior analyzer.

Classifies trading behavior archetype from profile + post history.
Pure computation. INV-15. B1.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["BehaviorProfile", "BehaviorAnalyzer"]

_ARCHETYPE_KEYWORDS: dict[str, list[str]] = {
    "scalper": ["scalp", "quick", "5min", "1min", "tick", "intraday", "day trade"],
    "swing_trader": ["swing", "weekly", "breakout", "hold", "overnight", "position"],
    "degen": ["ape", "yolo", "100x", "gem", "moon", "degen", "send it", "rekt"],
    "whale": ["size", "block", "institutional", "desk", "flow", "dark pool"],
    "analyst": ["analysis", "ta", "chart", "fibonacci", "support", "resistance", "rsi", "macd"],
}


@dataclass(frozen=True, slots=True)
class BehaviorProfile:
    source_id: str
    ts_ns: int
    archetype: str           # dominant archetype label
    archetype_scores: tuple[tuple[str, float], ...]  # sorted (archetype, score) pairs
    activity_level: str      # "low" | "medium" | "high"
    sentiment_bias: str      # "bullish" | "bearish" | "neutral"


class BehaviorAnalyzer:
    """Score trader archetypes from combined bio + post text."""

    def analyze(
        self,
        source_id: str,
        ts_ns: int,
        bio: str,
        posts: list[str],
        post_count: int,
    ) -> BehaviorProfile:
        combined = (bio + " " + " ".join(posts)).lower()
        scores = self._score_archetypes(combined)
        dominant = max(scores, key=lambda x: x[1])[0] if scores else "unknown"
        activity = self._activity_level(post_count)
        sentiment = self._sentiment(combined)
        return BehaviorProfile(
            source_id=source_id,
            ts_ns=ts_ns,
            archetype=dominant,
            archetype_scores=tuple(scores),
            activity_level=activity,
            sentiment_bias=sentiment,
        )

    def _score_archetypes(self, text: str) -> list[tuple[str, float]]:
        results: list[tuple[str, float]] = []
        total = max(len(text), 1)
        for archetype, keywords in _ARCHETYPE_KEYWORDS.items():
            hits = sum(text.count(kw) for kw in keywords)
            score = min(1.0, hits / 5.0)
            results.append((archetype, score))
        return sorted(results, key=lambda x: x[1], reverse=True)

    def _activity_level(self, post_count: int) -> str:
        if post_count >= 10_000:
            return "high"
        if post_count >= 1_000:
            return "medium"
        return "low"

    def _sentiment(self, text: str) -> str:
        bullish_words = ["bull", "long", "buy", "moon", "pump", "breakout", "bullish"]
        bearish_words = ["bear", "short", "sell", "dump", "crash", "breakdown", "bearish"]
        bull_score = sum(text.count(w) for w in bullish_words)
        bear_score = sum(text.count(w) for w in bearish_words)
        if bull_score > bear_score * 1.3:
            return "bullish"
        if bear_score > bull_score * 1.3:
            return "bearish"
        return "neutral"

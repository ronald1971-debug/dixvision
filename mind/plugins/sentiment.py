"""mind.plugins.sentiment — Sentiment Intelligence Plugin.

Processes sentiment signals from social media, news, and community sources.
Outputs confidence-weighted SentimentSignal into the intelligence pipeline.

Sources: X/Twitter, Reddit, StockTwits, Discord, Telegram (via canonical
normalizer). Raw trust ≤ 0.5 for external sources per governance policy.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from system import time_source


class SentimentPolarity(StrEnum):
    """Sentiment direction classification."""

    EXTREMELY_BULLISH = "EXTREMELY_BULLISH"
    BULLISH = "BULLISH"
    NEUTRAL = "NEUTRAL"
    BEARISH = "BEARISH"
    EXTREMELY_BEARISH = "EXTREMELY_BEARISH"


@dataclass(frozen=True, slots=True)
class SentimentReading:
    """Single sentiment observation after normalization."""

    symbol: str
    polarity: SentimentPolarity
    intensity: float
    source_platform: str
    sample_size: int
    confidence: float
    ts_ns: int = field(default_factory=time_source.wall_ns)


class SentimentPlugin:
    """Intelligence plugin for aggregated sentiment analysis.

    Consumes normalized social/news signals, computes rolling sentiment
    scores, and emits SentimentReading into the intelligence pipeline.
    """

    __slots__ = ("_lock", "_readings", "_window_size", "_active")

    def __init__(self, window_size: int = 100) -> None:
        self._lock = threading.Lock()
        self._readings: list[SentimentReading] = []
        self._window_size = window_size
        self._active = True

    @property
    def active(self) -> bool:
        return self._active

    def process(self, normalized_payload: dict[str, Any]) -> SentimentReading | None:
        """Process a normalized sentiment payload from the data pipeline.

        Args:
            normalized_payload: Output from the canonical normalizer with
                keys: text, source_platform, symbol, ts_ns, trust_score.

        Returns:
            SentimentReading if confidence threshold met, None otherwise.
        """
        if not self._active:
            return None

        trust = float(normalized_payload.get("trust_score", 0.0))
        if trust < 0.1:
            return None

        text = str(normalized_payload.get("text", ""))
        symbol = str(normalized_payload.get("symbol", "UNKNOWN"))
        source = str(normalized_payload.get("source_platform", "unknown"))

        polarity, intensity = self._analyze_text(text)

        confidence = min(trust * intensity, 0.5)  # External ≤ 0.5

        reading = SentimentReading(
            symbol=symbol,
            polarity=polarity,
            intensity=intensity,
            source_platform=source,
            sample_size=1,
            confidence=confidence,
        )

        with self._lock:
            self._readings.append(reading)
            if len(self._readings) > self._window_size:
                self._readings = self._readings[-self._window_size :]

        return reading

    def get_aggregate(self, symbol: str) -> SentimentReading | None:
        """Compute aggregate sentiment for a symbol over the rolling window."""
        with self._lock:
            readings_copy = list(self._readings)
        relevant = [r for r in readings_copy if r.symbol == symbol]
        if not relevant:
            return None

        avg_intensity = sum(r.intensity for r in relevant) / len(relevant)
        bullish_count = sum(
            1
            for r in relevant
            if r.polarity in (SentimentPolarity.BULLISH, SentimentPolarity.EXTREMELY_BULLISH)
        )
        bearish_count = sum(
            1
            for r in relevant
            if r.polarity in (SentimentPolarity.BEARISH, SentimentPolarity.EXTREMELY_BEARISH)
        )

        if bullish_count > bearish_count * 1.5:
            polarity = SentimentPolarity.BULLISH
        elif bearish_count > bullish_count * 1.5:
            polarity = SentimentPolarity.BEARISH
        else:
            polarity = SentimentPolarity.NEUTRAL

        return SentimentReading(
            symbol=symbol,
            polarity=polarity,
            intensity=avg_intensity,
            source_platform="aggregate",
            sample_size=len(relevant),
            confidence=min(avg_intensity * 0.5, 0.5),
        )

    def _analyze_text(self, text: str) -> tuple[SentimentPolarity, float]:
        """Basic keyword-based sentiment analysis.

        In production, this delegates to the ML sentiment model.
        """
        text_lower = text.lower()
        bullish_keywords = {"moon", "bullish", "pump", "breakout", "long", "buy", "rocket"}
        bearish_keywords = {"dump", "bearish", "crash", "short", "sell", "rug", "scam"}

        bull_score = sum(1 for kw in bullish_keywords if kw in text_lower)
        bear_score = sum(1 for kw in bearish_keywords if kw in text_lower)

        total = bull_score + bear_score
        if total == 0:
            return SentimentPolarity.NEUTRAL, 0.3

        intensity = min(total / 5.0, 1.0)
        if bull_score > bear_score:
            polarity = (
                SentimentPolarity.BULLISH if bull_score < 3 else SentimentPolarity.EXTREMELY_BULLISH
            )
        elif bear_score > bull_score:
            polarity = (
                SentimentPolarity.BEARISH if bear_score < 3 else SentimentPolarity.EXTREMELY_BEARISH
            )
        else:
            polarity = SentimentPolarity.NEUTRAL

        return polarity, intensity


__all__ = [
    "SentimentPlugin",
    "SentimentPolarity",
    "SentimentReading",
]

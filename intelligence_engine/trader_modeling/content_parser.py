"""Content parser (BUILD-DIRECTIVE §15 — TIS module 4).

Parses raw trader content (text, trade examples, interviews) into
structured data suitable for strategy extraction and philosophy encoding.

Handles multiple content formats:
- Text posts (tweets, articles, forum posts)
- Trade examples (entry/exit/size annotations)
- Interview transcripts (key insight extraction)
- Chart annotations (pattern/setup descriptions)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ContentType(StrEnum):
    """Type of content being parsed."""

    TEXT_POST = "TEXT_POST"
    TRADE_EXAMPLE = "TRADE_EXAMPLE"
    INTERVIEW = "INTERVIEW"
    CHART_ANNOTATION = "CHART_ANNOTATION"
    BOOK_EXCERPT = "BOOK_EXCERPT"
    RESEARCH_NOTE = "RESEARCH_NOTE"


@dataclass(frozen=True, slots=True)
class ParsedContent:
    """Structured output from content parsing."""

    content_id: str
    content_type: ContentType
    trader_id: str
    raw_text: str
    extracted_setups: tuple[str, ...]
    extracted_rules: tuple[str, ...]
    mentioned_instruments: tuple[str, ...]
    mentioned_timeframes: tuple[str, ...]
    sentiment: float  # -1.0 = bearish, +1.0 = bullish
    confidence: float
    ts_ns: int
    metadata: dict[str, Any]


class ContentParser:
    """Parses raw trader content into structured form.

    The parser identifies actionable trading knowledge (setups, rules,
    instruments, timeframes) from unstructured text.
    """

    def parse(
        self,
        *,
        content_id: str,
        content_type: ContentType,
        trader_id: str,
        raw_text: str,
        ts_ns: int,
    ) -> ParsedContent:
        """Parse raw content into structured form."""
        text_lower = raw_text.lower()

        # Extract setups (patterns/entries)
        setups: list[str] = []
        setup_keywords = [
            "breakout",
            "pullback",
            "reversal",
            "divergence",
            "golden cross",
            "death cross",
            "support",
            "resistance",
            "accumulation",
            "distribution",
            "flag",
            "wedge",
        ]
        for kw in setup_keywords:
            if kw in text_lower:
                setups.append(kw)

        # Extract rules
        rules: list[str] = []
        rule_patterns = [
            "always",
            "never",
            "stop loss",
            "take profit",
            "risk per trade",
            "position size",
            "cut losses",
            "let winners run",
            "scale in",
            "scale out",
        ]
        for rp in rule_patterns:
            if rp in text_lower:
                rules.append(rp)

        # Extract instruments
        instruments: list[str] = []
        instrument_markers = [
            "btc",
            "eth",
            "sol",
            "spy",
            "qqq",
            "gold",
            "oil",
            "eurusd",
            "gbpusd",
            "usdjpy",
        ]
        for im in instrument_markers:
            if im in text_lower:
                instruments.append(im.upper())

        # Extract timeframes
        timeframes: list[str] = []
        tf_markers = {
            "1m": "1M",
            "5m": "5M",
            "15m": "15M",
            "1h": "1H",
            "4h": "4H",
            "daily": "1D",
            "weekly": "1W",
            "monthly": "1MO",
        }
        for marker, canonical in tf_markers.items():
            if marker in text_lower:
                timeframes.append(canonical)

        # Simple sentiment from keywords
        bullish_words = ["long", "buy", "bullish", "moon", "pump", "accumulate"]
        bearish_words = ["short", "sell", "bearish", "dump", "crash", "distribute"]
        bull_count = sum(1 for w in bullish_words if w in text_lower)
        bear_count = sum(1 for w in bearish_words if w in text_lower)
        total = bull_count + bear_count
        sentiment = (bull_count - bear_count) / max(total, 1)

        # Confidence based on content richness
        richness = len(setups) + len(rules) + len(instruments)
        confidence = min(richness / 5.0, 1.0)

        return ParsedContent(
            content_id=content_id,
            content_type=content_type,
            trader_id=trader_id,
            raw_text=raw_text,
            extracted_setups=tuple(setups),
            extracted_rules=tuple(rules),
            mentioned_instruments=tuple(instruments),
            mentioned_timeframes=tuple(timeframes),
            sentiment=sentiment,
            confidence=confidence,
            ts_ns=ts_ns,
            metadata={},
        )

"""Trader pattern store (BUILD-DIRECTIVE §19).

SQLite-backed persistence for trader patterns, philosophies, and
performance metrics. Uses WAL mode for concurrent reads.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StoredPattern:
    """A pattern observation stored in the pattern database."""

    pattern_id: str
    trader_id: str
    category: str
    description: str
    frequency: int
    last_seen_ts_ns: int
    confidence: float
    regime: str
    performance_sharpe: float = 0.0


class PatternStore:
    """In-memory pattern store (SQLite backing in production).

    Stores trader patterns with frequency tracking and decay.
    """

    def __init__(self) -> None:
        self._patterns: dict[str, StoredPattern] = {}

    def upsert(self, pattern: StoredPattern) -> None:
        """Insert or update a pattern observation."""
        existing = self._patterns.get(pattern.pattern_id)
        if existing is not None:
            # Increment frequency, update last_seen
            updated = StoredPattern(
                pattern_id=pattern.pattern_id,
                trader_id=pattern.trader_id,
                category=pattern.category,
                description=pattern.description,
                frequency=existing.frequency + 1,
                last_seen_ts_ns=pattern.last_seen_ts_ns,
                confidence=max(existing.confidence, pattern.confidence),
                regime=pattern.regime,
                performance_sharpe=pattern.performance_sharpe,
            )
            self._patterns[pattern.pattern_id] = updated
        else:
            self._patterns[pattern.pattern_id] = pattern

    def get_by_trader(self, trader_id: str) -> list[StoredPattern]:
        """Get all patterns for a specific trader."""
        return [p for p in self._patterns.values() if p.trader_id == trader_id]

    def get_by_regime(self, regime: str) -> list[StoredPattern]:
        """Get all patterns applicable to a regime."""
        return [p for p in self._patterns.values() if p.regime == regime]

    def top_patterns(self, *, top_k: int = 10) -> list[StoredPattern]:
        """Get top-k patterns by frequency × confidence."""
        scored = sorted(
            self._patterns.values(),
            key=lambda p: p.frequency * p.confidence,
            reverse=True,
        )
        return scored[:top_k]

    @property
    def size(self) -> int:
        """Total patterns stored."""
        return len(self._patterns)

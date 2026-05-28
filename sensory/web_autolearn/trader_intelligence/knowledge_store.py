"""Knowledge store for validated trader patterns.

The final stage of the pipeline: validated, decay-weighted patterns are
stored here for consumption by Indira and the evolution engine.

Patterns are versioned, ledgerable, and indexed by:
- Trader source (for attribution)
- Regime (for context-aware retrieval)
- Embedding (for similarity search via TraderEmbeddingStore)

All reads go through decay weighting — stale patterns are returned
with reduced weight and eventually expired.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from learning_engine.trader_abstraction.decay_weighter import DecayWeighter
from sensory.web_autolearn.trader_intelligence.contracts import (
    TraderPattern,
)


@dataclass(frozen=True, slots=True)
class StoreStats:
    """Summary statistics for the knowledge store."""

    total_patterns: int
    active_patterns: int
    expired_patterns: int
    by_category: dict[str, int]
    by_strategy_type: dict[str, int]
    avg_confidence: float
    avg_decay_weight: float


class TraderKnowledgeStore:
    """Validated pattern store with decay weighting and retrieval.

    Patterns enter here only after passing the full pipeline:
    Source → Credibility → Parse → Extract → Encode → Abstract →
    Validate → **Store**.

    Indira reads from here, never from raw sources.
    """

    def __init__(
        self,
        *,
        decay_half_life_days: float = 90.0,
        min_decay_weight: float = 0.01,
    ) -> None:
        self._patterns: dict[str, TraderPattern] = {}
        self._by_source: dict[str, list[str]] = defaultdict(list)
        self._by_regime: dict[str, list[str]] = defaultdict(list)
        self._by_strategy_type: dict[str, list[str]] = defaultdict(list)
        self._decayer = DecayWeighter(
            half_life_days=decay_half_life_days,
            min_weight=min_decay_weight,
        )

    def ingest(self, pattern: TraderPattern) -> None:
        """Add a validated pattern to the store."""
        pid = pattern.pattern_id
        if pid in self._patterns:
            raise ValueError(f"duplicate pattern_id: {pid}")
        self._patterns[pid] = pattern
        self._by_source[pattern.source_trader_id].append(pid)
        self._by_strategy_type[pattern.strategy_type].append(pid)
        for cond in pattern.context_conditions:
            self._by_regime[cond].append(pid)

    def get(self, pattern_id: str) -> TraderPattern | None:
        """Retrieve a pattern by ID."""
        return self._patterns.get(pattern_id)

    def query_by_regime(
        self,
        regime: str,
        *,
        now_ns: int,
        top_k: int = 20,
    ) -> list[tuple[TraderPattern, float]]:
        """Retrieve patterns applicable to a regime, decay-weighted.

        Returns (pattern, decayed_weight) pairs sorted by weight desc.
        Expired patterns are excluded.
        """
        pids = self._by_regime.get(regime, [])
        return self._decay_and_rank(pids, now_ns=now_ns, top_k=top_k)

    def query_by_source(
        self,
        source_trader_id: str,
        *,
        now_ns: int,
        top_k: int = 50,
    ) -> list[tuple[TraderPattern, float]]:
        """Retrieve patterns from a specific trader source."""
        pids = self._by_source.get(source_trader_id, [])
        return self._decay_and_rank(pids, now_ns=now_ns, top_k=top_k)

    def query_by_strategy_type(
        self,
        strategy_type: str,
        *,
        now_ns: int,
        top_k: int = 20,
    ) -> list[tuple[TraderPattern, float]]:
        """Retrieve patterns of a specific strategy type."""
        pids = self._by_strategy_type.get(strategy_type, [])
        return self._decay_and_rank(pids, now_ns=now_ns, top_k=top_k)

    def all_active(self, *, now_ns: int) -> list[tuple[TraderPattern, float]]:
        """Return all non-expired patterns with decay weights."""
        return self._decay_and_rank(
            list(self._patterns.keys()),
            now_ns=now_ns,
            top_k=len(self._patterns),
        )

    def stats(self, *, now_ns: int) -> StoreStats:
        """Compute summary statistics."""
        active = 0
        expired = 0
        total_conf = 0.0
        total_decay = 0.0
        by_cat: dict[str, int] = defaultdict(int)
        by_type: dict[str, int] = defaultdict(int)

        for p in self._patterns.values():
            result = self._decayer.decay(
                weight=p.confidence,
                pattern_ts_ns=p.ts_ns,
                now_ns=now_ns,
            )
            if result.expired:
                expired += 1
            else:
                active += 1
                total_conf += p.confidence
                total_decay += result.decayed_weight
            by_cat[p.source_category.value] = by_cat.get(p.source_category.value, 0) + 1
            by_type[p.strategy_type] = by_type.get(p.strategy_type, 0) + 1

        return StoreStats(
            total_patterns=len(self._patterns),
            active_patterns=active,
            expired_patterns=expired,
            by_category=dict(by_cat),
            by_strategy_type=dict(by_type),
            avg_confidence=total_conf / active if active > 0 else 0.0,
            avg_decay_weight=total_decay / active if active > 0 else 0.0,
        )

    def _decay_and_rank(
        self,
        pattern_ids: list[str],
        *,
        now_ns: int,
        top_k: int,
    ) -> list[tuple[TraderPattern, float]]:
        """Apply decay and return top-k non-expired patterns."""
        scored: list[tuple[TraderPattern, float]] = []
        for pid in pattern_ids:
            p = self._patterns.get(pid)
            if p is None:
                continue
            result = self._decayer.decay(
                weight=p.confidence,
                pattern_ts_ns=p.ts_ns,
                now_ns=now_ns,
            )
            if not result.expired:
                scored.append((p, result.decayed_weight))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    @property
    def size(self) -> int:
        return len(self._patterns)

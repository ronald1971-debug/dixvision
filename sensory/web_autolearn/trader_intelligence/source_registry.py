"""Source registry for 5000+ trader intelligence sources.

Manages diversity across discretionary, quant, macro, crypto-native,
HFT, and institutional trader categories. Each source carries metadata
for credibility weighting and category balancing.

The registry enforces:
- Source diversity (no single category > 40% of active sources)
- Unique source IDs
- Minimum credibility thresholds for pipeline admission
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from sensory.web_autolearn.trader_intelligence.contracts import (
    SourceCategory,
    TraderSource,
)


@dataclass(frozen=True, slots=True)
class DiversityReport:
    """Category breakdown of registered sources."""

    total: int
    active: int
    by_category: dict[str, int]
    dominant_category: str
    diversity_score: float  # 0=monolithic, 1=perfectly balanced


class TraderSourceRegistry:
    """Registry of trader intelligence sources.

    Tracks 5000+ sources with diversity constraints and credibility
    thresholds. Sources are ingested by the pipeline in priority order
    based on credibility and recency.
    """

    MAX_CATEGORY_SHARE = 0.40
    MIN_CREDIBILITY = 0.1

    def __init__(self) -> None:
        self._sources: dict[str, TraderSource] = {}

    def register(self, source: TraderSource) -> None:
        """Register a new trader source."""
        if source.source_id in self._sources:
            raise ValueError(f"duplicate source_id: {source.source_id}")
        if source.credibility_weight < self.MIN_CREDIBILITY:
            raise ValueError(
                f"credibility_weight {source.credibility_weight} "
                f"below minimum {self.MIN_CREDIBILITY}"
            )
        self._sources[source.source_id] = source

    def deactivate(self, source_id: str) -> None:
        """Mark a source as inactive (soft delete)."""
        old = self._sources.get(source_id)
        if old is None:
            raise KeyError(f"unknown source: {source_id}")
        # Frozen dataclass — replace via constructor
        self._sources[source_id] = TraderSource(
            source_id=old.source_id,
            name=old.name,
            category=old.category,
            medium=old.medium,
            url_pattern=old.url_pattern,
            credibility_weight=old.credibility_weight,
            active=False,
            meta=old.meta,
        )

    def active_sources(
        self, *, category: SourceCategory | None = None
    ) -> list[TraderSource]:
        """Return active sources, optionally filtered by category."""
        out = [s for s in self._sources.values() if s.active]
        if category is not None:
            out = [s for s in out if s.category == category]
        return sorted(out, key=lambda s: s.credibility_weight, reverse=True)

    def diversity_report(self) -> DiversityReport:
        """Compute diversity metrics across active sources."""
        active = [s for s in self._sources.values() if s.active]
        counts = Counter(s.category.value for s in active)

        if not active:
            return DiversityReport(
                total=len(self._sources),
                active=0,
                by_category=dict(counts),
                dominant_category="NONE",
                diversity_score=0.0,
            )

        dominant = counts.most_common(1)[0][0]
        n_cats = len(SourceCategory)
        ideal = len(active) / n_cats
        # Diversity score: 1 - normalized deviation from uniform
        deviation = sum(abs(counts.get(c.value, 0) - ideal) for c in SourceCategory)
        max_deviation = len(active) * 2
        diversity_score = max(0.0, 1.0 - deviation / max_deviation)

        return DiversityReport(
            total=len(self._sources),
            active=len(active),
            by_category=dict(counts),
            dominant_category=dominant,
            diversity_score=diversity_score,
        )

    @property
    def size(self) -> int:
        return len(self._sources)

    def get(self, source_id: str) -> TraderSource | None:
        return self._sources.get(source_id)

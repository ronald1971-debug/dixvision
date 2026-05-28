"""Narrative alignment (BUILD-DIRECTIVE §15 — TIS module 13).

Aligns trader narratives with current market narratives to detect
convergence/divergence. When multiple credible traders align on a
narrative (e.g., "risk-off due to macro"), this strengthens confidence.
When they diverge, it signals regime uncertainty.

Narrative clusters feed into the meta-controller's confidence scaling.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NarrativeSignal:
    """A narrative signal from a trader or market."""

    narrative_id: str
    source: str  # trader_id or "market"
    theme: str  # e.g., "risk_off", "btc_supercycle", "fed_pivot"
    conviction: float  # 0=weak, 1=strong
    ts_ns: int


@dataclass(frozen=True, slots=True)
class NarrativeAlignment:
    """Alignment measurement between traders and market narratives."""

    theme: str
    aligned_traders: tuple[str, ...]
    divergent_traders: tuple[str, ...]
    alignment_score: float  # 0=no consensus, 1=full consensus
    confidence_boost: float  # how much to boost/reduce confidence
    ts_ns: int


class NarrativeAlignmentEngine:
    """Tracks narrative alignment across traders and market signals.

    High alignment = high confidence in the narrative direction.
    Low alignment = regime uncertainty, reduce position sizes.
    """

    def __init__(self, *, decay_window_ns: int = 86400 * 10**9) -> None:
        self._decay_window_ns = decay_window_ns
        self._signals: list[NarrativeSignal] = []
        self._max_signals = 10000

    def ingest_signal(self, signal: NarrativeSignal) -> None:
        """Ingest a new narrative signal."""
        self._signals.append(signal)
        if len(self._signals) > self._max_signals:
            self._signals = self._signals[-self._max_signals :]

    def measure_alignment(self, *, theme: str, ts_ns: int) -> NarrativeAlignment:
        """Measure current alignment for a narrative theme."""
        # Get recent signals for this theme
        cutoff = ts_ns - self._decay_window_ns
        relevant = [s for s in self._signals if s.theme == theme and s.ts_ns >= cutoff]

        if not relevant:
            return NarrativeAlignment(
                theme=theme,
                aligned_traders=(),
                divergent_traders=(),
                alignment_score=0.0,
                confidence_boost=0.0,
                ts_ns=ts_ns,
            )

        # Group by source, take latest signal per source
        latest_by_source: dict[str, NarrativeSignal] = {}
        for s in relevant:
            existing = latest_by_source.get(s.source)
            if existing is None or s.ts_ns > existing.ts_ns:
                latest_by_source[s.source] = s

        # Aligned = conviction > 0.5, divergent = conviction < 0.3
        aligned: list[str] = []
        divergent: list[str] = []
        for source, signal in latest_by_source.items():
            if signal.conviction >= 0.5:
                aligned.append(source)
            elif signal.conviction <= 0.3:
                divergent.append(source)

        total_sources = len(latest_by_source)
        alignment_score = len(aligned) / max(total_sources, 1)

        # Confidence boost: high alignment boosts, low alignment reduces
        if alignment_score >= 0.7:
            confidence_boost = 0.2 * alignment_score
        elif alignment_score <= 0.3:
            confidence_boost = -0.1 * (1.0 - alignment_score)
        else:
            confidence_boost = 0.0

        return NarrativeAlignment(
            theme=theme,
            aligned_traders=tuple(aligned),
            divergent_traders=tuple(divergent),
            alignment_score=alignment_score,
            confidence_boost=confidence_boost,
            ts_ns=ts_ns,
        )

    def get_active_themes(self, *, ts_ns: int, min_signals: int = 3) -> list[str]:
        """Get themes with recent activity above threshold."""
        cutoff = ts_ns - self._decay_window_ns
        theme_counts: dict[str, int] = {}
        for s in self._signals:
            if s.ts_ns >= cutoff:
                theme_counts[s.theme] = theme_counts.get(s.theme, 0) + 1
        return [t for t, c in theme_counts.items() if c >= min_signals]

    def strongest_narrative(self, *, ts_ns: int) -> NarrativeAlignment | None:
        """Get the narrative with strongest current alignment."""
        themes = self.get_active_themes(ts_ns=ts_ns)
        if not themes:
            return None
        best: NarrativeAlignment | None = None
        for theme in themes:
            alignment = self.measure_alignment(theme=theme, ts_ns=ts_ns)
            if best is None or alignment.alignment_score > best.alignment_score:
                best = alignment
        return best

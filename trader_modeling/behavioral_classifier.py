"""trader_modeling.behavioral_classifier — Classify signal batches into archetypes.

Maps a SignalBatch (normalized behavioral signals from order flow) to one
of the canonical trader archetypes.  Classification is rule-based with
confidence scoring — no ML dependency, fully deterministic.

Archetypes:
  HFT_SCALPER      — ultra-high speed, high aggression, small size
  MOMENTUM_TRADER  — directional bias, medium aggression, regime-aligned
  MEAN_REVERTER    — counter-trend, medium size, low regime alignment
  MACRO_PLAYER     — slow, large size, regime-sensitive
  QUANT_SYSTEMATIC — balanced, high speed, regime-neutral
  RETAIL_NOISE     — random direction, low speed, small size

Authority (B1): imports only core.*, trader_modeling.*.
INV-15: no wall-clock reads; ts_ns is caller-supplied.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from trader_modeling.profile_extractor import SignalBatch

# ---------------------------------------------------------------------------
# Archetype identifiers
# ---------------------------------------------------------------------------

ARCHETYPE_HFT_SCALPER: Final[str] = "hft_scalper"
ARCHETYPE_MOMENTUM: Final[str] = "momentum_trader"
ARCHETYPE_MEAN_REVERTER: Final[str] = "mean_reverter"
ARCHETYPE_MACRO: Final[str] = "macro_player"
ARCHETYPE_QUANT: Final[str] = "quant_systematic"
ARCHETYPE_RETAIL: Final[str] = "retail_noise"

ALL_ARCHETYPES: Final[tuple[str, ...]] = (
    ARCHETYPE_HFT_SCALPER,
    ARCHETYPE_MOMENTUM,
    ARCHETYPE_MEAN_REVERTER,
    ARCHETYPE_MACRO,
    ARCHETYPE_QUANT,
    ARCHETYPE_RETAIL,
)


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    """Output of one behavioral classification pass."""

    ts_ns: int
    symbol: str
    archetype: str
    confidence: float               # [0, 1]
    scores: dict[str, float]        # archetype → raw score
    signal_count: int
    mean_aggression: float
    mean_direction: float
    mean_speed: float


class BehavioralClassifier:
    """Rule-based classifier mapping signal batches to trader archetypes.

    Scoring:
    Each archetype has a scoring function that returns a value in [0, 1].
    The archetype with the highest score wins; confidence = winner_score /
    (winner_score + second_score) — measures separation between top two.
    """

    def classify(self, batch: SignalBatch, ts_ns: int) -> ClassificationResult:
        """Classify a SignalBatch and return the dominant archetype."""
        aggr = batch.mean_aggression
        dirn = abs(batch.mean_direction)
        spd = batch.mean_speed
        # regime alignment: mean across signals
        regime_align = (
            sum(s.regime_alignment for s in batch.signals) / len(batch.signals)
            if batch.signals else 0.5
        )
        # size diversity: stddev of size_rank as proxy for size consistency
        sizes = [s.size_rank for s in batch.signals]
        mean_size = sum(sizes) / max(1, len(sizes))

        scores: dict[str, float] = {
            ARCHETYPE_HFT_SCALPER:    self._score_hft(aggr, spd, mean_size),
            ARCHETYPE_MOMENTUM:       self._score_momentum(aggr, dirn, regime_align),
            ARCHETYPE_MEAN_REVERTER:  self._score_reverter(dirn, regime_align, mean_size),
            ARCHETYPE_MACRO:          self._score_macro(spd, mean_size, regime_align),
            ARCHETYPE_QUANT:          self._score_quant(spd, aggr, dirn),
            ARCHETYPE_RETAIL:         self._score_retail(spd, dirn, mean_size),
        }

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        winner_name, winner_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        confidence = winner_score / max(1e-6, winner_score + second_score)

        return ClassificationResult(
            ts_ns=ts_ns,
            symbol=batch.symbol,
            archetype=winner_name,
            confidence=round(confidence, 4),
            scores={k: round(v, 4) for k, v in scores.items()},
            signal_count=batch.window_size,
            mean_aggression=round(aggr, 4),
            mean_direction=round(batch.mean_direction, 4),
            mean_speed=round(spd, 4),
        )

    # ------------------------------------------------------------------
    # Scoring functions — each returns a value in [0, 1]
    # ------------------------------------------------------------------

    @staticmethod
    def _score_hft(aggression: float, speed: float, mean_size: float) -> float:
        # HFT: very fast, high aggression, small trades
        size_inv = 1.0 - mean_size  # small size → high score
        return (0.4 * speed + 0.35 * aggression + 0.25 * size_inv)

    @staticmethod
    def _score_momentum(aggression: float, directionality: float, regime_align: float) -> float:
        # Momentum: directional, moderate aggression, regime-aligned
        return (0.35 * directionality + 0.30 * regime_align + 0.35 * aggression)

    @staticmethod
    def _score_reverter(directionality: float, regime_align: float, mean_size: float) -> float:
        # Mean reversion: counter-trend (low directionality), medium size
        counter = 1.0 - directionality
        counter_regime = 1.0 - regime_align
        return (0.40 * counter + 0.30 * counter_regime + 0.30 * mean_size)

    @staticmethod
    def _score_macro(speed: float, mean_size: float, regime_align: float) -> float:
        # Macro: slow, large size, regime-sensitive
        speed_inv = 1.0 - speed
        return (0.35 * speed_inv + 0.40 * mean_size + 0.25 * regime_align)

    @staticmethod
    def _score_quant(speed: float, aggression: float, directionality: float) -> float:
        # Quant: balanced speed and aggression, lower directionality
        balance = 1.0 - abs(speed - aggression)
        neutral_dir = 1.0 - directionality
        return (0.40 * balance + 0.35 * speed + 0.25 * neutral_dir)

    @staticmethod
    def _score_retail(speed: float, directionality: float, mean_size: float) -> float:
        # Retail: slow, noisy direction, small size
        speed_inv = 1.0 - speed
        dir_noise = 1.0 - directionality
        size_inv = 1.0 - mean_size
        return (0.35 * speed_inv + 0.35 * dir_noise + 0.30 * size_inv)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_classifier: BehavioralClassifier | None = None


def get_behavioral_classifier() -> BehavioralClassifier:
    """Return the process-wide BehavioralClassifier singleton."""
    global _classifier
    if _classifier is None:
        _classifier = BehavioralClassifier()
    return _classifier


__all__ = [
    "ALL_ARCHETYPES",
    "ARCHETYPE_HFT_SCALPER",
    "ARCHETYPE_MACRO",
    "ARCHETYPE_MEAN_REVERTER",
    "ARCHETYPE_MOMENTUM",
    "ARCHETYPE_QUANT",
    "ARCHETYPE_RETAIL",
    "BehavioralClassifier",
    "ClassificationResult",
    "get_behavioral_classifier",
]

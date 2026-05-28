"""MAC-01 — HMM/Bayesian regime switching classifier.

Pure computation. No clock reads. INV-15 deterministic.
B1: No imports from execution/governance/learning/evolution engines.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = ["RegimeClassification", "RegimeClassifier"]

_REGIMES = ("bull", "bear", "ranging", "volatile")


@dataclass(frozen=True, slots=True)
class RegimeClassification:
    ts_ns: int
    regime: str
    confidence: float
    probabilities: tuple[tuple[str, float], ...]  # (regime, prob) sorted


class RegimeClassifier:
    """Classify market regime via Bayesian update on observed features.

    The default model is a simple linear-discriminant heuristic on
    (return_zscore, volatility_zscore, trend_strength). A proper
    HMM implementation may be swapped in via the research-acceptance gate.
    """

    def __init__(self, smoothing: float = 0.1) -> None:
        self._smoothing = smoothing
        self._prior: dict[str, float] = {r: 0.25 for r in _REGIMES}

    def classify(
        self,
        ts_ns: int,
        *,
        return_zscore: float,
        volatility_zscore: float,
        trend_strength: float,   # 0.0 = flat, 1.0 = strong trend
    ) -> RegimeClassification:
        scores: dict[str, float] = {
            "bull": max(0.0, return_zscore) * 0.5 + trend_strength * 0.3 + (1.0 - volatility_zscore * 0.1),
            "bear": max(0.0, -return_zscore) * 0.5 + trend_strength * 0.3 + (1.0 - volatility_zscore * 0.1),
            "ranging": (1.0 - trend_strength) * 0.6 + max(0.0, 1.0 - volatility_zscore) * 0.4,
            "volatile": max(0.0, volatility_zscore) * 0.7 + (1.0 - trend_strength) * 0.3,
        }
        total = sum(scores.values()) or 1.0
        probs = {r: (scores[r] / total) * (1 - self._smoothing) + self._smoothing / 4 for r in _REGIMES}
        total_p = sum(probs.values())
        probs = {r: p / total_p for r, p in probs.items()}

        best = max(probs, key=lambda r: probs[r])
        return RegimeClassification(
            ts_ns=ts_ns,
            regime=best,
            confidence=probs[best],
            probabilities=tuple(sorted(probs.items(), key=lambda x: -x[1])),
        )

    def update_prior(self, regime: str, weight: float) -> None:
        """Soft-update prior toward observed regime."""
        if regime not in self._prior:
            return
        for r in self._prior:
            self._prior[r] = self._prior[r] * (1 - weight)
        self._prior[regime] += weight
        total = sum(self._prior.values())
        self._prior = {r: p / total for r, p in self._prior.items()}

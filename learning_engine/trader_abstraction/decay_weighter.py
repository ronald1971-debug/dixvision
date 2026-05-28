"""Temporal decay weighting for trader patterns.

Implements ``weight = e^(-λ * Δt)`` so older patterns lose relevance
over time. This prevents stale strategies from dominating the
knowledge store.

Pure function — no IO, no clock reads (INV-15). Caller supplies
``now_ns`` and the pattern's ``ts_ns``; the function returns a
decay-adjusted weight.

Decay parameters:
- ``half_life_days``: number of days for weight to halve (default 90)
- ``min_weight``: floor below which patterns are considered expired
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_NS_PER_DAY = 86_400_000_000_000


@dataclass(frozen=True, slots=True)
class DecayResult:
    """Result of decay weighting."""

    original_weight: float
    decayed_weight: float
    age_days: float
    expired: bool


class DecayWeighter:
    """Applies exponential time-decay to pattern weights.

    ``weight_out = weight_in * e^(-λ * age_days)``

    where ``λ = ln(2) / half_life_days``.
    """

    def __init__(
        self,
        *,
        half_life_days: float = 90.0,
        min_weight: float = 0.01,
    ) -> None:
        if half_life_days <= 0:
            raise ValueError("half_life_days must be positive")
        self._lambda = math.log(2) / half_life_days
        self._min_weight = min_weight
        self._half_life_days = half_life_days

    def decay(
        self,
        *,
        weight: float,
        pattern_ts_ns: int,
        now_ns: int,
    ) -> DecayResult:
        """Apply temporal decay to a pattern weight.

        Parameters
        ----------
        weight : float
            Original pattern weight / confidence.
        pattern_ts_ns : int
            Timestamp when the pattern was created (nanoseconds).
        now_ns : int
            Current timestamp (nanoseconds).
        """
        delta_ns = max(0, now_ns - pattern_ts_ns)
        age_days = delta_ns / _NS_PER_DAY
        decayed = weight * math.exp(-self._lambda * age_days)
        expired = decayed < self._min_weight
        return DecayResult(
            original_weight=weight,
            decayed_weight=decayed,
            age_days=age_days,
            expired=expired,
        )

    def batch_decay(
        self,
        *,
        patterns: list[tuple[str, float, int]],
        now_ns: int,
    ) -> list[tuple[str, DecayResult]]:
        """Decay a batch of (pattern_id, weight, ts_ns) tuples.

        Returns list of (pattern_id, DecayResult) sorted by decayed
        weight descending.
        """
        results = [
            (pid, self.decay(weight=w, pattern_ts_ns=ts, now_ns=now_ns))
            for pid, w, ts in patterns
        ]
        results.sort(key=lambda x: x[1].decayed_weight, reverse=True)
        return results

    @property
    def half_life_days(self) -> float:
        return self._half_life_days

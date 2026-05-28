"""XAS-02 — lead/lag detection between asset pairs.

Detects which asset leads the other by computing lagged cross-correlations.
Pure function. INV-15 deterministic. B1 compliant.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = ["LeadLagResult", "LeadLagDetector"]


@dataclass(frozen=True, slots=True)
class LeadLagResult:
    symbol_a: str
    symbol_b: str
    lag_bars: int       # positive = A leads B; negative = B leads A
    correlation: float
    confidence: float   # 0.0–1.0, abs(correlation) as proxy


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs) / n) or 1e-12
    sy = math.sqrt(sum((y - my) ** 2 for y in ys) / n) or 1e-12
    return max(-1.0, min(1.0, cov / (sx * sy)))


class LeadLagDetector:
    """Detect lead/lag via lagged cross-correlation over a price series."""

    def __init__(self, max_lag: int = 10) -> None:
        self._max_lag = max_lag

    def detect(
        self,
        symbol_a: str,
        prices_a: list[float],
        symbol_b: str,
        prices_b: list[float],
    ) -> LeadLagResult:
        n = min(len(prices_a), len(prices_b))
        if n < self._max_lag + 2:
            return LeadLagResult(symbol_a, symbol_b, 0, 0.0, 0.0)

        pa = prices_a[-n:]
        pb = prices_b[-n:]
        best_lag, best_corr = 0, 0.0

        for lag in range(-self._max_lag, self._max_lag + 1):
            if lag >= 0:
                corr = _pearson(pa[:n - lag], pb[lag:]) if lag < n else 0.0
            else:
                corr = _pearson(pa[-lag:], pb[:n + lag]) if -lag < n else 0.0
            if abs(corr) > abs(best_corr):
                best_corr = corr
                best_lag = lag

        return LeadLagResult(
            symbol_a=symbol_a,
            symbol_b=symbol_b,
            lag_bars=best_lag,
            correlation=best_corr,
            confidence=abs(best_corr),
        )

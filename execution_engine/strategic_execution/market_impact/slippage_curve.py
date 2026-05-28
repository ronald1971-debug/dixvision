"""SE-05 — slippage curve builder.

Builds a price-impact curve from order size vs observed slippage samples.
Pure computation. INV-15. B1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = ["SlippagePoint", "SlippageCurve"]


@dataclass(frozen=True, slots=True)
class SlippagePoint:
    qty_pct_adv: float    # order size as % of ADV
    slippage_bps: float   # observed slippage in bps


class SlippageCurve:
    """Fit and query a log-linear slippage curve.

    Uses least-squares fit: slippage_bps = a + b * ln(qty_pct_adv).
    Falls back to a linear model if fewer than 2 samples.
    """

    def __init__(self) -> None:
        self._samples: list[SlippagePoint] = []
        self._a: float = 0.0
        self._b: float = 0.0
        self._fitted: bool = False

    def add_sample(self, qty_pct_adv: float, slippage_bps: float) -> None:
        if qty_pct_adv <= 0:
            raise ValueError("qty_pct_adv must be positive")
        self._samples.append(SlippagePoint(qty_pct_adv=qty_pct_adv, slippage_bps=slippage_bps))
        if len(self._samples) >= 2:
            self._fit()

    def _fit(self) -> None:
        xs = [math.log(s.qty_pct_adv) for s in self._samples]
        ys = [s.slippage_bps for s in self._samples]
        n = len(xs)
        sum_x = sum(xs)
        sum_y = sum(ys)
        sum_xx = sum(x * x for x in xs)
        sum_xy = sum(x * y for x, y in zip(xs, ys))
        denom = n * sum_xx - sum_x ** 2
        if abs(denom) < 1e-12:
            self._a = sum_y / n
            self._b = 0.0
        else:
            self._b = (n * sum_xy - sum_x * sum_y) / denom
            self._a = (sum_y - self._b * sum_x) / n
        self._fitted = True

    def predict(self, qty_pct_adv: float) -> float:
        if qty_pct_adv <= 0:
            raise ValueError("qty_pct_adv must be positive")
        if not self._fitted:
            return 0.0
        return max(0.0, self._a + self._b * math.log(qty_pct_adv))

    @property
    def sample_count(self) -> int:
        return len(self._samples)

    def samples(self) -> tuple[SlippagePoint, ...]:
        return tuple(self._samples)

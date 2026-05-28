"""CorrelationMonitor — detects correlation regime changes.

Monitors rolling correlations between assets/factors and alerts when
historical relationships break down. Correlation breaks often precede
major market events and represent potential alpha sources.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from enum import StrEnum


class BreakType(StrEnum):
    DECORRELATION = "DECORRELATION"  # were correlated, now aren't
    NEW_CORRELATION = "NEW_CORRELATION"  # weren't correlated, now are
    REVERSAL = "REVERSAL"  # correlation flipped sign


@dataclass(frozen=True, slots=True)
class CorrelationBreak:
    """Detected correlation regime change."""

    pair: tuple[str, str]
    break_type: BreakType
    historical_correlation: float
    current_correlation: float
    change_magnitude: float
    confidence: float
    implication: str


class CorrelationMonitor:
    """Monitors rolling correlations for structural breaks.

    Detects when:
    - Two assets that moved together decouple
    - Two unrelated assets start moving together
    - Correlation sign flips
    """

    def __init__(
        self,
        *,
        lookback: int = 50,
        break_threshold: float = 0.4,
    ) -> None:
        self._lookback = lookback
        self._threshold = break_threshold
        self._series: dict[str, deque[float]] = {}

    def update(self, symbol: str, value: float) -> None:
        """Update price/return series for a symbol."""
        if symbol not in self._series:
            self._series[symbol] = deque(maxlen=self._lookback * 2)
        self._series[symbol].append(value)

    def scan(self, pairs: list[tuple[str, str]] | None = None) -> list[CorrelationBreak]:
        """Scan for correlation breaks across all or specified pairs."""
        breaks: list[CorrelationBreak] = []
        symbols = list(self._series.keys())

        if pairs is None:
            pairs = [
                (symbols[i], symbols[j])
                for i in range(len(symbols))
                for j in range(i + 1, len(symbols))
            ]

        for a, b in pairs:
            sa = self._series.get(a)
            sb = self._series.get(b)
            if sa is None or sb is None:
                continue
            if len(sa) < self._lookback or len(sb) < self._lookback:
                continue

            la = list(sa)
            lb = list(sb)
            n = min(len(la), len(lb))
            la = la[-n:]
            lb = lb[-n:]

            # Historical correlation (first half)
            mid = n // 2
            hist_corr = self._correlation(la[:mid], lb[:mid])
            curr_corr = self._correlation(la[mid:], lb[mid:])

            change = abs(curr_corr - hist_corr)
            if change < self._threshold:
                continue

            # Classify break type
            if abs(hist_corr) > 0.5 and abs(curr_corr) < 0.2:
                btype = BreakType.DECORRELATION
                impl = f"{a}/{b} decoupled: potential divergence trade."
            elif abs(hist_corr) < 0.2 and abs(curr_corr) > 0.5:
                btype = BreakType.NEW_CORRELATION
                impl = f"{a}/{b} now correlated: check for common driver."
            elif hist_corr * curr_corr < 0 and abs(change) > 0.6:
                btype = BreakType.REVERSAL
                impl = f"{a}/{b} correlation flipped: structural regime change."
            else:
                continue

            breaks.append(
                CorrelationBreak(
                    pair=(a, b),
                    break_type=btype,
                    historical_correlation=hist_corr,
                    current_correlation=curr_corr,
                    change_magnitude=change,
                    confidence=min(change / 0.8, 0.95),
                    implication=impl,
                )
            )

        return breaks

    @staticmethod
    def _correlation(xs: list[float], ys: list[float]) -> float:
        """Pearson correlation."""
        n = len(xs)
        if n < 5:
            return 0.0
        mx = sum(xs) / n
        my = sum(ys) / n
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
        dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
        dy = math.sqrt(sum((y - my) ** 2 for y in ys))
        if dx * dy == 0:
            return 0.0
        return num / (dx * dy)

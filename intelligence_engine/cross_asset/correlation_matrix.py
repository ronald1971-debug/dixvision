"""XAS-01 — rolling cross-asset correlation matrix.

Pure computation. No clocks, no I/O. INV-15 deterministic.
B1: No imports from execution_engine/governance_engine/learning_engine/evolution_engine.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any

__all__ = ["RollingCorrelation", "CorrelationMatrix"]


@dataclass(frozen=True, slots=True)
class RollingCorrelation:
    symbol_a: str
    symbol_b: str
    correlation: float  # -1.0 to 1.0
    window_size: int
    sample_count: int


class CorrelationMatrix:
    """Rolling Pearson correlation matrix over a fixed window.

    Window is maintained as a deque per symbol pair; correlation is
    computed lazily on demand. All computation is pure given the
    caller-supplied price sequence.
    """

    def __init__(self, window: int = 60) -> None:
        self._window = window
        self._prices: dict[str, deque[float]] = {}

    def update(self, symbol: str, price: float) -> None:
        if symbol not in self._prices:
            self._prices[symbol] = deque(maxlen=self._window)
        self._prices[symbol].append(price)

    def correlation(self, symbol_a: str, symbol_b: str) -> RollingCorrelation:
        pa = list(self._prices.get(symbol_a, []))
        pb = list(self._prices.get(symbol_b, []))
        n = min(len(pa), len(pb))
        if n < 2:
            return RollingCorrelation(symbol_a, symbol_b, 0.0, self._window, n)
        pa, pb = pa[-n:], pb[-n:]
        mean_a = sum(pa) / n
        mean_b = sum(pb) / n
        cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(pa, pb)) / n
        std_a = math.sqrt(sum((a - mean_a) ** 2 for a in pa) / n) or 1e-12
        std_b = math.sqrt(sum((b - mean_b) ** 2 for b in pb) / n) or 1e-12
        r = max(-1.0, min(1.0, cov / (std_a * std_b)))
        return RollingCorrelation(symbol_a, symbol_b, r, self._window, n)

    def all_pairs(self) -> tuple[RollingCorrelation, ...]:
        symbols = sorted(self._prices.keys())
        pairs = []
        for i, a in enumerate(symbols):
            for b in symbols[i + 1:]:
                pairs.append(self.correlation(a, b))
        return tuple(pairs)

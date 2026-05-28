"""XAS-03 — cross-asset shock contagion detector.

Detects when a shock in one asset propagates to others via sudden
correlation spikes. Pure computation. INV-15. B1 compliant.
"""

from __future__ import annotations

from dataclasses import dataclass

from intelligence_engine.cross_asset.correlation_matrix import CorrelationMatrix

__all__ = ["ContagionEvent", "ContagionDetector"]


@dataclass(frozen=True, slots=True)
class ContagionEvent:
    ts_ns: int
    source_symbol: str
    affected_symbols: tuple[str, ...]
    correlation_spike: float  # magnitude of correlation change
    detail: str = ""


class ContagionDetector:
    """Detects contagion events via rolling correlation divergence.

    A contagion event fires when the rolling correlation between
    the source symbol and any other symbol spikes above ``threshold``
    relative to its recent baseline.
    """

    def __init__(
        self,
        window: int = 60,
        baseline_window: int = 300,
        threshold: float = 0.30,
    ) -> None:
        self._current = CorrelationMatrix(window=window)
        self._baseline = CorrelationMatrix(window=baseline_window)
        self._threshold = threshold

    def update(self, symbol: str, price: float) -> None:
        self._current.update(symbol, price)
        self._baseline.update(symbol, price)

    def scan(self, source: str, ts_ns: int) -> ContagionEvent | None:
        affected: list[str] = []
        max_spike = 0.0
        for pair in self._current.all_pairs():
            if source not in (pair.symbol_a, pair.symbol_b):
                continue
            other = pair.symbol_b if pair.symbol_a == source else pair.symbol_a
            baseline = self._baseline.correlation(pair.symbol_a, pair.symbol_b)
            spike = abs(pair.correlation) - abs(baseline.correlation)
            if spike >= self._threshold:
                affected.append(other)
                max_spike = max(max_spike, spike)

        if not affected:
            return None
        return ContagionEvent(
            ts_ns=ts_ns,
            source_symbol=source,
            affected_symbols=tuple(sorted(affected)),
            correlation_spike=max_spike,
            detail=f"contagion from {source} spike={max_spike:.3f}",
        )

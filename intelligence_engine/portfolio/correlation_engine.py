"""
intelligence_engine/portfolio/correlation_engine.py
DIX VISION v42.2 — Correlation Engine

Tracks rolling pairwise Pearson correlations between strategy / symbol
P&L streams. High correlation = hidden concentration risk; low
correlation = genuine diversification.

Used by the portfolio allocator to penalise correlated strategy pairs
and by the capital scheduler to set diversification multipliers.
"""

from __future__ import annotations

import math
import threading
from collections import deque
from typing import Any

_WINDOW = 100


class CorrelationEngine:
    """
    Rolling pairwise Pearson correlation tracker.

    Thread-safe. Callers call update() after each P&L observation;
    the engine maintains a bounded deque per symbol.
    """

    def __init__(self, window: int = _WINDOW) -> None:
        self._window = window
        self._lock = threading.Lock()
        # symbol → deque[float]
        self._series: dict[str, deque[float]] = {}

    # ------------------------------------------------------------------
    # Data ingestion
    # ------------------------------------------------------------------

    def update(self, symbol: str, pnl: float, ts_ns: int = 0) -> None:
        """Record a P&L observation for a symbol."""
        with self._lock:
            if symbol not in self._series:
                self._series[symbol] = deque(maxlen=self._window)
            self._series[symbol].append(pnl)

    # ------------------------------------------------------------------
    # Correlation queries
    # ------------------------------------------------------------------

    def get_correlation(self, sym_a: str, sym_b: str) -> float:
        """
        Return Pearson correlation between two symbols' P&L series.

        Returns 0.0 if either series has < 2 samples or if one of the
        symbols is unknown.
        """
        with self._lock:
            a = list(self._series.get(sym_a, []))
            b = list(self._series.get(sym_b, []))

        n = min(len(a), len(b))
        if n < 2:
            return 0.0
        a, b = a[-n:], b[-n:]
        return _pearson(a, b)

    def get_correlation_matrix(self) -> dict[str, dict[str, float]]:
        """Return full N×N pairwise correlation matrix as nested dict."""
        with self._lock:
            symbols = list(self._series.keys())
        matrix: dict[str, dict[str, float]] = {}
        for sym_a in symbols:
            matrix[sym_a] = {}
            for sym_b in symbols:
                if sym_a == sym_b:
                    matrix[sym_a][sym_b] = 1.0
                else:
                    matrix[sym_a][sym_b] = self.get_correlation(sym_a, sym_b)
        return matrix

    def diversification_score(self) -> float:
        """
        Mean absolute pairwise correlation across all symbol pairs.

        0.0 = perfectly uncorrelated (maximum diversification).
        1.0 = perfectly correlated (no diversification benefit).
        """
        with self._lock:
            symbols = list(self._series.keys())
        if len(symbols) < 2:
            return 0.0
        pairs = [
            abs(self.get_correlation(a, b))
            for i, a in enumerate(symbols)
            for b in symbols[i + 1:]
        ]
        return sum(pairs) / len(pairs) if pairs else 0.0

    def tracked_symbols(self) -> list[str]:
        with self._lock:
            return list(self._series.keys())

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "tracked_symbols": len(self._series),
                "window": self._window,
                "diversification_score": self.diversification_score(),
            }


def _pearson(a: list[float], b: list[float]) -> float:
    """Pure Pearson correlation for two equal-length lists."""
    n = len(a)
    if n < 2:
        return 0.0
    mean_a = sum(a) / n
    mean_b = sum(b) / n
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b)) / n
    std_a = math.sqrt(sum((x - mean_a) ** 2 for x in a) / n)
    std_b = math.sqrt(sum((y - mean_b) ** 2 for y in b) / n)
    if std_a < 1e-12 or std_b < 1e-12:
        return 0.0
    return cov / (std_a * std_b)


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: CorrelationEngine | None = None
_lock = threading.Lock()


def get_correlation_engine() -> CorrelationEngine:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = CorrelationEngine()
    return _instance


__all__ = ["CorrelationEngine", "get_correlation_engine"]

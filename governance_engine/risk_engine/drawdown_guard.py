"""Drawdown guard — pure check against a percentage threshold."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DrawdownResult:
    """Outcome of a drawdown guard check."""

    passed: bool
    drawdown_pct: float
    threshold_pct: float


class DrawdownGuard:
    """Checks whether ``drawdown_pct`` stays within ``threshold_pct``. Pure."""

    __slots__ = ("threshold_pct",)

    def __init__(self, threshold_pct: float = 0.05) -> None:
        self.threshold_pct = threshold_pct

    def check(self, drawdown_pct: float) -> DrawdownResult:
        passed = drawdown_pct <= self.threshold_pct
        return DrawdownResult(
            passed=passed,
            drawdown_pct=drawdown_pct,
            threshold_pct=self.threshold_pct,
        )


__all__ = ["DrawdownResult", "DrawdownGuard"]

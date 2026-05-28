"""SE-02 — Almgren-Chriss style optimal execution trajectory.

Computes the optimal trade schedule to minimise market impact cost
plus timing risk. Pure computation. INV-15. B1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = ["OptimalExecutionPlan", "ExecutionSlice", "OptimalExecutor"]


@dataclass(frozen=True, slots=True)
class ExecutionSlice:
    slice_index: int
    qty: float
    expected_price: float
    expected_impact_bps: float


@dataclass(frozen=True, slots=True)
class OptimalExecutionPlan:
    symbol: str
    ts_ns: int
    total_qty: float
    slices: tuple[ExecutionSlice, ...]
    total_expected_impact_bps: float
    strategy: str  # "TWAP", "VWAP", "AC"


class OptimalExecutor:
    """Almgren-Chriss optimal execution trajectory.

    Default strategy: TWAP (time-weighted average). AC (full
    Almgren-Chriss) requires volatility + impact params.
    """

    def __init__(
        self,
        n_slices: int = 10,
        impact_per_pct: float = 2.0,  # bps impact per 1% of ADV
    ) -> None:
        self._n = n_slices
        self._impact_per_pct = impact_per_pct

    def plan_twap(
        self,
        symbol: str,
        ts_ns: int,
        total_qty: float,
        adv: float,
        mid_price: float,
    ) -> OptimalExecutionPlan:
        slice_qty = total_qty / self._n
        pct_adv = (slice_qty / adv * 100) if adv > 0 else 0.0
        impact_per_slice_bps = pct_adv * self._impact_per_pct
        cumulative_impact = 0.0
        slices: list[ExecutionSlice] = []
        for i in range(self._n):
            cumulative_impact += impact_per_slice_bps
            slices.append(ExecutionSlice(
                slice_index=i,
                qty=slice_qty,
                expected_price=mid_price * (1 + cumulative_impact / 10000),
                expected_impact_bps=impact_per_slice_bps,
            ))
        return OptimalExecutionPlan(
            symbol=symbol, ts_ns=ts_ns, total_qty=total_qty,
            slices=tuple(slices),
            total_expected_impact_bps=cumulative_impact,
            strategy="TWAP",
        )

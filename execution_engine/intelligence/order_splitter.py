"""OrderSplitter — minimizes market impact by splitting large orders.

Strategies:
- TWAP: time-weighted average price (split evenly over time)
- VWAP: volume-weighted (split proportional to expected volume)
- Iceberg: show only a fraction at a time
- Adaptive: adjust split based on real-time fill rates
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from execution_engine.intelligence.liquidity_model import LiquidityModel


class SplitStrategy(StrEnum):
    TWAP = "TWAP"
    VWAP = "VWAP"
    ICEBERG = "ICEBERG"
    ADAPTIVE = "ADAPTIVE"


@dataclass(frozen=True, slots=True)
class OrderSlice:
    """One slice of a split order."""

    slice_index: int
    size_usd: float
    delay_ms: int  # delay before placing this slice
    price_limit_offset_bps: float  # limit price offset from mid


@dataclass(frozen=True, slots=True)
class SplitPlan:
    """Complete execution plan for a split order."""

    symbol: str
    total_size_usd: float
    strategy: SplitStrategy
    slices: tuple[OrderSlice, ...]
    estimated_total_slippage_bps: float
    estimated_duration_ms: int


class OrderSplitter:
    """Generates split execution plans for large orders.

    Deterministic: same (order_size, liquidity_state, strategy) → same plan.
    """

    def __init__(
        self,
        liquidity_model: LiquidityModel,
        *,
        max_participation_rate: float = 0.05,  # max 5% of available liquidity per slice
        default_strategy: SplitStrategy = SplitStrategy.ADAPTIVE,
    ) -> None:
        self._liq = liquidity_model
        self._max_participation = max_participation_rate
        self._default_strategy = default_strategy

    def plan(
        self,
        symbol: str,
        total_size_usd: float,
        *,
        strategy: SplitStrategy | None = None,
        urgency: float = 0.5,  # 0=patient, 1=urgent
    ) -> SplitPlan:
        """Generate a split plan for the given order."""
        strat = strategy or self._default_strategy
        snap = self._liq.latest(symbol)

        # Determine number of slices
        if snap is None:
            # No liquidity data — be very conservative
            n_slices = max(int(total_size_usd / 1000), 5)
        else:
            available = (snap.bid_depth_usd + snap.ask_depth_usd) / 2
            max_per_slice = available * self._max_participation
            n_slices = max(int(total_size_usd / max_per_slice) + 1, 2)

        # Adjust for urgency
        n_slices = max(int(n_slices * (1.5 - urgency)), 2)

        # Generate slices
        slices: list[OrderSlice] = []
        slice_size = total_size_usd / n_slices

        for i in range(n_slices):
            if strat == SplitStrategy.TWAP:
                delay = int(i * 1000 * (1.5 - urgency))
                limit_offset = 0.0
            elif strat == SplitStrategy.ICEBERG:
                delay = int(i * 500)
                limit_offset = -1.0  # passive
            elif strat == SplitStrategy.ADAPTIVE:
                # Frontload slightly, then slow down
                delay = int(i * 800 * (1.5 - urgency))
                limit_offset = -0.5 if i < n_slices // 2 else 0.5
            else:  # VWAP
                delay = int(i * 1200)
                limit_offset = 0.0

            slices.append(
                OrderSlice(
                    slice_index=i,
                    size_usd=slice_size,
                    delay_ms=delay,
                    price_limit_offset_bps=limit_offset,
                )
            )

        duration = slices[-1].delay_ms if slices else 0
        # Estimate total slippage (less than single large order)
        est_slip = (snap.spread_bps if snap else 5.0) * 0.6  # splitting reduces by ~40%

        return SplitPlan(
            symbol=symbol,
            total_size_usd=total_size_usd,
            strategy=strat,
            slices=tuple(slices),
            estimated_total_slippage_bps=est_slip,
            estimated_duration_ms=duration,
        )

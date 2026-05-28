"""learning_engine/performance_analysis/slippage_analysis.py
DIX VISION v42.2 — Slippage Analysis

Measures execution slippage: the difference between the expected fill
price (signal price or mid-price at order submission) and the actual
fill price. Provides per-strategy and per-venue slippage statistics.

Pure functions + frozen dataclasses (INV-15 replay determinism).
No IO, no clock reads. Callers supply timestamps explicitly.

Tier: OFFLINE — slow-cadence analytics, never on hot path.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SlippageRecord:
    """One slippage observation for a single fill."""
    strategy_id: str
    venue: str
    symbol: str
    side: str               # BUY | SELL
    signal_price: float     # expected price at submission
    fill_price: float       # actual execution price
    qty: float
    slippage_bps: float     # signed basis-points slippage
    slippage_usd: float     # signed dollar slippage
    ts_ns: int


@dataclass(frozen=True, slots=True)
class SlippageStats:
    """Aggregate slippage statistics over a sample of trades."""
    strategy_id: str
    venue: str
    sample_count: int
    mean_bps: float
    std_bps: float
    p50_bps: float
    p95_bps: float
    total_cost_usd: float
    ts_ns: int


def compute_slippage(
    strategy_id: str,
    venue: str,
    symbol: str,
    side: str,
    signal_price: float,
    fill_price: float,
    qty: float,
    ts_ns: int,
) -> SlippageRecord:
    """Compute signed slippage for a single fill."""
    if signal_price <= 0:
        slippage_bps = 0.0
        slippage_usd = 0.0
    else:
        # Positive slippage = we paid more (BUY) or received less (SELL)
        side_sign = 1.0 if side.upper() == "BUY" else -1.0
        slippage_bps = (fill_price - signal_price) / signal_price * 10_000 * side_sign
        slippage_usd = (fill_price - signal_price) * qty * side_sign
    return SlippageRecord(
        strategy_id=strategy_id,
        venue=venue,
        symbol=symbol,
        side=side,
        signal_price=signal_price,
        fill_price=fill_price,
        qty=qty,
        slippage_bps=slippage_bps,
        slippage_usd=slippage_usd,
        ts_ns=ts_ns,
    )


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = max(0, int(math.ceil(pct / 100.0 * len(sorted_vals))) - 1)
    return sorted_vals[idx]


def aggregate_slippage(
    records: list[SlippageRecord],
    strategy_id: str,
    venue: str,
    ts_ns: int,
) -> SlippageStats:
    """Aggregate a list of SlippageRecords into summary statistics."""
    filtered = [r for r in records if r.strategy_id == strategy_id and r.venue == venue]
    if not filtered:
        return SlippageStats(
            strategy_id=strategy_id,
            venue=venue,
            sample_count=0,
            mean_bps=0.0,
            std_bps=0.0,
            p50_bps=0.0,
            p95_bps=0.0,
            total_cost_usd=0.0,
            ts_ns=ts_ns,
        )

    bps_vals = [r.slippage_bps for r in filtered]
    sorted_bps = sorted(bps_vals)
    mean_bps = sum(bps_vals) / len(bps_vals)
    var = sum((x - mean_bps) ** 2 for x in bps_vals) / len(bps_vals)
    std_bps = math.sqrt(var)
    total_cost_usd = sum(r.slippage_usd for r in filtered)

    return SlippageStats(
        strategy_id=strategy_id,
        venue=venue,
        sample_count=len(filtered),
        mean_bps=mean_bps,
        std_bps=std_bps,
        p50_bps=_percentile(sorted_bps, 50),
        p95_bps=_percentile(sorted_bps, 95),
        total_cost_usd=total_cost_usd,
        ts_ns=ts_ns,
    )


__all__ = [
    "SlippageRecord",
    "SlippageStats",
    "aggregate_slippage",
    "compute_slippage",
]

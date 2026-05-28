"""learning_engine/performance_analysis/latency_impact.py
DIX VISION v42.2 — Latency Impact Analysis

Measures the P&L impact of execution latency: how much value was lost
(or gained) due to price movement during the latency window between
signal generation and order fill.

Pure functions + frozen dataclasses (INV-15 replay determinism).
No IO, no clock reads. Tier: OFFLINE analytics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LatencyImpactRecord:
    """P&L impact attributed to execution latency for one trade."""
    strategy_id: str
    venue: str
    symbol: str
    side: str
    signal_ts_ns: int       # when signal was generated
    fill_ts_ns: int         # when fill was confirmed
    latency_ns: int         # fill_ts_ns - signal_ts_ns
    signal_price: float
    fill_price: float
    qty: float
    impact_bps: float       # adverse price move during latency in bps
    impact_usd: float


@dataclass(frozen=True, slots=True)
class LatencyImpactStats:
    """Aggregated latency impact statistics."""
    strategy_id: str
    sample_count: int
    mean_latency_ms: float
    p95_latency_ms: float
    mean_impact_bps: float
    total_impact_usd: float
    ts_ns: int


def compute_latency_impact(
    strategy_id: str,
    venue: str,
    symbol: str,
    side: str,
    signal_ts_ns: int,
    fill_ts_ns: int,
    signal_price: float,
    fill_price: float,
    qty: float,
) -> LatencyImpactRecord:
    """Compute latency impact for one fill."""
    latency_ns = max(0, fill_ts_ns - signal_ts_ns)
    side_sign = 1.0 if side.upper() == "BUY" else -1.0
    if signal_price > 0:
        impact_bps = (fill_price - signal_price) / signal_price * 10_000 * side_sign
        impact_usd = (fill_price - signal_price) * qty * side_sign
    else:
        impact_bps = 0.0
        impact_usd = 0.0
    return LatencyImpactRecord(
        strategy_id=strategy_id,
        venue=venue,
        symbol=symbol,
        side=side,
        signal_ts_ns=signal_ts_ns,
        fill_ts_ns=fill_ts_ns,
        latency_ns=latency_ns,
        signal_price=signal_price,
        fill_price=fill_price,
        qty=qty,
        impact_bps=impact_bps,
        impact_usd=impact_usd,
    )


def _pct(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = max(0, int(math.ceil(p / 100.0 * len(sorted_vals))) - 1)
    return sorted_vals[idx]


def aggregate_latency_impact(
    records: list[LatencyImpactRecord],
    strategy_id: str,
    ts_ns: int,
) -> LatencyImpactStats:
    filtered = [r for r in records if r.strategy_id == strategy_id]
    if not filtered:
        return LatencyImpactStats(
            strategy_id=strategy_id,
            sample_count=0,
            mean_latency_ms=0.0,
            p95_latency_ms=0.0,
            mean_impact_bps=0.0,
            total_impact_usd=0.0,
            ts_ns=ts_ns,
        )
    lat_ms = sorted(r.latency_ns / 1e6 for r in filtered)
    impact_bps = [r.impact_bps for r in filtered]
    return LatencyImpactStats(
        strategy_id=strategy_id,
        sample_count=len(filtered),
        mean_latency_ms=sum(lat_ms) / len(lat_ms),
        p95_latency_ms=_pct(lat_ms, 95),
        mean_impact_bps=sum(impact_bps) / len(impact_bps),
        total_impact_usd=sum(r.impact_usd for r in filtered),
        ts_ns=ts_ns,
    )


__all__ = [
    "LatencyImpactRecord",
    "LatencyImpactStats",
    "aggregate_latency_impact",
    "compute_latency_impact",
]

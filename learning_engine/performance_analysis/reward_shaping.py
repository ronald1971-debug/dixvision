"""learning_engine/performance_analysis/reward_shaping.py
DIX VISION v42.2 — Reward Shaping

Transforms raw P&L into shaped reward signals for reinforcement
learning. Supports multiple shaping strategies:
  - RAW: R = realised_pnl
  - RISK_ADJUSTED: R = pnl / (drawdown + eps)
  - SHARPE_INCREMENTAL: R = incremental Sharpe contribution
  - POTENTIAL_BASED: Φ(s') - Φ(s) shaping (convergence-safe)

Pure functions + frozen dataclasses (INV-15 replay determinism).
No IO, no clock reads. Tier: OFFLINE analytics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class RewardShapeKind(StrEnum):
    RAW = "RAW"
    RISK_ADJUSTED = "RISK_ADJUSTED"
    SHARPE_INCREMENTAL = "SHARPE_INCREMENTAL"
    POTENTIAL_BASED = "POTENTIAL_BASED"


@dataclass(frozen=True, slots=True)
class ShapingConfig:
    kind: RewardShapeKind = RewardShapeKind.RISK_ADJUSTED
    drawdown_eps: float = 1e-4
    sharpe_window: int = 20
    potential_gamma: float = 0.99


@dataclass(frozen=True, slots=True)
class ShapedReward:
    """Shaped reward for one step."""
    strategy_id: str
    raw_pnl: float
    shaped_reward: float
    kind: RewardShapeKind
    ts_ns: int


def shape_raw(pnl: float, strategy_id: str, ts_ns: int) -> ShapedReward:
    return ShapedReward(
        strategy_id=strategy_id,
        raw_pnl=pnl,
        shaped_reward=pnl,
        kind=RewardShapeKind.RAW,
        ts_ns=ts_ns,
    )


def shape_risk_adjusted(
    pnl: float,
    drawdown: float,
    strategy_id: str,
    ts_ns: int,
    eps: float = 1e-4,
) -> ShapedReward:
    shaped = pnl / (abs(drawdown) + eps)
    return ShapedReward(
        strategy_id=strategy_id,
        raw_pnl=pnl,
        shaped_reward=shaped,
        kind=RewardShapeKind.RISK_ADJUSTED,
        ts_ns=ts_ns,
    )


def shape_sharpe_incremental(
    pnl: float,
    history: tuple[float, ...],
    strategy_id: str,
    ts_ns: int,
) -> ShapedReward:
    """Incremental Sharpe: difference in Sharpe when pnl is added."""
    if len(history) < 2:
        return ShapedReward(
            strategy_id=strategy_id,
            raw_pnl=pnl,
            shaped_reward=0.0,
            kind=RewardShapeKind.SHARPE_INCREMENTAL,
            ts_ns=ts_ns,
        )

    def _sharpe(vals: tuple[float, ...]) -> float:
        n = len(vals)
        if n < 2:
            return 0.0
        mean = sum(vals) / n
        var = sum((x - mean) ** 2 for x in vals) / n
        std = math.sqrt(var)
        return mean / std if std > 1e-12 else 0.0

    before = _sharpe(history)
    after = _sharpe(history + (pnl,))
    return ShapedReward(
        strategy_id=strategy_id,
        raw_pnl=pnl,
        shaped_reward=after - before,
        kind=RewardShapeKind.SHARPE_INCREMENTAL,
        ts_ns=ts_ns,
    )


def shape_potential_based(
    pnl: float,
    prev_potential: float,
    curr_potential: float,
    strategy_id: str,
    ts_ns: int,
    gamma: float = 0.99,
) -> ShapedReward:
    """Potential-based shaping: R' = R + γ·Φ(s') - Φ(s)."""
    shaped = pnl + gamma * curr_potential - prev_potential
    return ShapedReward(
        strategy_id=strategy_id,
        raw_pnl=pnl,
        shaped_reward=shaped,
        kind=RewardShapeKind.POTENTIAL_BASED,
        ts_ns=ts_ns,
    )


def shape(
    pnl: float,
    strategy_id: str,
    ts_ns: int,
    config: ShapingConfig | None = None,
    *,
    drawdown: float = 0.0,
    history: tuple[float, ...] = (),
    prev_potential: float = 0.0,
    curr_potential: float = 0.0,
) -> ShapedReward:
    """Dispatch to the configured shaping function."""
    cfg = config or ShapingConfig()
    if cfg.kind == RewardShapeKind.RAW:
        return shape_raw(pnl, strategy_id, ts_ns)
    if cfg.kind == RewardShapeKind.RISK_ADJUSTED:
        return shape_risk_adjusted(pnl, drawdown, strategy_id, ts_ns, cfg.drawdown_eps)
    if cfg.kind == RewardShapeKind.SHARPE_INCREMENTAL:
        return shape_sharpe_incremental(pnl, history, strategy_id, ts_ns)
    return shape_potential_based(pnl, prev_potential, curr_potential, strategy_id, ts_ns, cfg.potential_gamma)


__all__ = [
    "RewardShapeKind",
    "ShapedReward",
    "ShapingConfig",
    "shape",
    "shape_potential_based",
    "shape_raw",
    "shape_risk_adjusted",
    "shape_sharpe_incremental",
]

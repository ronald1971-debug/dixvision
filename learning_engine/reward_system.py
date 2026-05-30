"""RewardSystem — multi-factor reward engineering for RL/learning loops.

Elite reward ≠ raw PnL. True reward is:
  reward = f(pnl, drawdown, risk_adjusted, execution_quality,
             consistency, regime_correctness, slippage_penalty)

This closes the mathematical loop between decisions and learning.
Pure / deterministic (INV-15): same inputs → same reward.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RewardWeights:
    """Configurable weights for reward factors."""

    pnl: float = 0.30
    risk_adjusted: float = 0.20
    drawdown_penalty: float = 0.15
    execution_quality: float = 0.10
    consistency: float = 0.10
    regime_correctness: float = 0.10
    slippage_penalty: float = 0.05


@dataclass(frozen=True, slots=True)
class TradeOutcome:
    """Raw outcome of a single trade or decision."""

    pnl_usd: float
    holding_period_ns: int
    entry_slippage_bps: float
    exit_slippage_bps: float
    intended_size: float
    actual_size: float
    regime_at_entry: str
    regime_predicted: str
    peak_pnl_usd: float  # highest PnL during hold (for drawdown calc)
    portfolio_drawdown_pct: float  # portfolio-level drawdown at close


@dataclass(frozen=True, slots=True)
class RewardSignal:
    """Computed reward signal for a trade."""

    raw_pnl_reward: float
    risk_adjusted_reward: float
    drawdown_penalty: float
    execution_reward: float
    consistency_reward: float
    regime_reward: float
    slippage_penalty: float
    composite_reward: float
    factors: dict[str, float]


class RewardSystem:
    """Multi-factor reward computation engine.

    Does NOT use `reward = pnl`. Uses a composite function:
      composite = Σ(weight_i × factor_i)

    Where factors include risk-adjusted return, drawdown penalty,
    execution quality, consistency, regime correctness, and slippage.
    """

    def __init__(self, weights: RewardWeights | None = None) -> None:
        self._weights = weights or RewardWeights()
        self._history: deque[float] = deque(maxlen=100)  # bounded rolling PnL for consistency

    @property
    def weights(self) -> RewardWeights:
        return self._weights

    def compute(self, outcome: TradeOutcome) -> RewardSignal:
        """Compute composite reward from a trade outcome."""
        # Factor 1: PnL reward (normalized, clipped)
        raw_pnl = _sigmoid_normalize(outcome.pnl_usd, scale=1000.0)

        # Factor 2: Risk-adjusted (Sharpe-like: pnl / volatility)
        risk_adj = self._risk_adjusted_factor(outcome)

        # Factor 3: Drawdown penalty (penalize trades during high drawdown)
        dd_penalty = -min(outcome.portfolio_drawdown_pct * 2.0, 1.0)

        # Factor 4: Execution quality (fill vs intended)
        exec_quality = self._execution_quality(outcome)

        # Factor 5: Consistency (reward steady returns, penalize variance)
        consistency = self._consistency_factor(outcome.pnl_usd)

        # Factor 6: Regime correctness (did prediction match reality?)
        regime_reward = 1.0 if outcome.regime_at_entry == outcome.regime_predicted else -0.3

        # Factor 7: Slippage penalty
        total_slippage = outcome.entry_slippage_bps + outcome.exit_slippage_bps
        slip_penalty = -min(total_slippage / 20.0, 1.0)  # penalize above 20bps

        # Composite
        w = self._weights
        composite = (
            w.pnl * raw_pnl
            + w.risk_adjusted * risk_adj
            + w.drawdown_penalty * dd_penalty
            + w.execution_quality * exec_quality
            + w.consistency * consistency
            + w.regime_correctness * regime_reward
            + w.slippage_penalty * slip_penalty
        )

        factors = {
            "pnl": raw_pnl,
            "risk_adjusted": risk_adj,
            "drawdown_penalty": dd_penalty,
            "execution_quality": exec_quality,
            "consistency": consistency,
            "regime_correctness": regime_reward,
            "slippage_penalty": slip_penalty,
        }

        return RewardSignal(
            raw_pnl_reward=raw_pnl,
            risk_adjusted_reward=risk_adj,
            drawdown_penalty=dd_penalty,
            execution_reward=exec_quality,
            consistency_reward=consistency,
            regime_reward=regime_reward,
            slippage_penalty=slip_penalty,
            composite_reward=composite,
            factors=factors,
        )

    def _risk_adjusted_factor(self, outcome: TradeOutcome) -> float:
        """Risk-adjusted return: penalize trades that took too much risk."""
        if outcome.peak_pnl_usd <= 0:
            return _sigmoid_normalize(outcome.pnl_usd, scale=500.0) * 0.5
        # How much of peak PnL was captured
        capture_ratio = outcome.pnl_usd / outcome.peak_pnl_usd if outcome.peak_pnl_usd > 0 else 0
        return min(max(capture_ratio, -1.0), 1.0)

    def _execution_quality(self, outcome: TradeOutcome) -> float:
        """How well did execution match intent."""
        if outcome.intended_size <= 0:
            return 0.0
        fill_ratio = outcome.actual_size / outcome.intended_size
        # Perfect fill = 1.0, partial = proportional, overfill = penalized
        if fill_ratio > 1.0:
            return max(1.0 - (fill_ratio - 1.0), 0.0)
        return fill_ratio

    def _consistency_factor(self, pnl: float) -> float:
        """Reward consistent returns, penalize variance."""
        self._history.append(pnl)
        if len(self._history) < 5:
            return 0.0
        # Use coefficient of variation (lower = more consistent)
        recent = self._history[-20:]
        mean = sum(recent) / len(recent)
        variance = sum((x - mean) ** 2 for x in recent) / len(recent)
        std = math.sqrt(variance) if variance > 0 else 0.001
        cv = abs(std / mean) if abs(mean) > 0.001 else 10.0
        # Invert: low CV = high reward
        return max(1.0 - cv / 5.0, -1.0)


def _sigmoid_normalize(value: float, scale: float = 1000.0) -> float:
    """Map value to [-1, 1] using tanh normalization."""
    return math.tanh(value / scale)

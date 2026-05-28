"""PnL Decomposition — break total PnL into component sources.

Decomposes returns into:
- Alpha: signal-driven excess return
- Beta: market exposure return
- Execution: slippage + timing costs
- Regime: regime-correct vs regime-wrong contribution
- Timing: early/late entry/exit cost
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PnLComponents:
    """Decomposed PnL attribution."""

    total_pnl: float
    alpha_pnl: float  # signal-driven
    beta_pnl: float  # market exposure
    execution_pnl: float  # slippage cost (negative = cost)
    timing_pnl: float  # early/late penalty
    regime_pnl: float  # regime-correctness contribution
    unexplained_pnl: float  # residual


class PnLDecomposer:
    """Decomposes trade PnL into attributable factors.

    Pure math, no IO (INV-15).
    """

    def decompose(
        self,
        *,
        total_pnl: float,
        market_return_bps: float,
        position_beta: float,
        entry_slippage_bps: float,
        exit_slippage_bps: float,
        position_size: float,
        optimal_entry_pnl: float,
        actual_entry_pnl: float,
        regime_correct: bool,
    ) -> PnLComponents:
        """Decompose a single trade's PnL."""
        # Beta component: how much came from market exposure
        beta_pnl = market_return_bps * position_beta * position_size / 10000.0

        # Execution cost
        execution_pnl = -(entry_slippage_bps + exit_slippage_bps) * position_size / 10000.0

        # Timing: difference between optimal and actual entry
        timing_pnl = actual_entry_pnl - optimal_entry_pnl

        # Regime bonus/penalty
        regime_pnl = abs(total_pnl) * (0.1 if regime_correct else -0.1)

        # Alpha is the residual after removing beta, execution, timing
        alpha_pnl = total_pnl - beta_pnl - execution_pnl - timing_pnl - regime_pnl
        unexplained = 0.0  # fully decomposed

        return PnLComponents(
            total_pnl=total_pnl,
            alpha_pnl=alpha_pnl,
            beta_pnl=beta_pnl,
            execution_pnl=execution_pnl,
            timing_pnl=timing_pnl,
            regime_pnl=regime_pnl,
            unexplained_pnl=unexplained,
        )

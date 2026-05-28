"""KillPolicy — rules for removing underperforming strategies.

Strategies die when:
1. Allocation drops below minimum threshold (arena handles this)
2. Max drawdown exceeds hard limit
3. Consecutive losses exceed patience
4. Regime fitness drops to zero (strategy invalid in current regime)
"""

from __future__ import annotations

from dataclasses import dataclass

from intelligence_engine.strategy_arena.arena_engine import StrategySlot, StrategyState


@dataclass(frozen=True, slots=True)
class KillReason:
    """Why a strategy was killed."""

    strategy_id: str
    reason: str
    detail: str


@dataclass(frozen=True, slots=True)
class KillPolicy:
    """Configurable kill thresholds."""

    max_drawdown_pct: float = 0.20  # 20% max drawdown
    max_consecutive_losses: int = 15
    min_regime_fit: float = 0.10  # below 10% regime fit = invalid
    min_sharpe_after_incubation: float = -0.5  # negative Sharpe = kill

    def should_kill(self, slot: StrategySlot) -> KillReason | None:
        """Return kill reason if strategy should be removed, else None."""
        if slot.state == StrategyState.KILLED:
            return None

        if slot.max_drawdown_pct > self.max_drawdown_pct:
            return KillReason(
                strategy_id=slot.strategy_id,
                reason="MAX_DRAWDOWN_EXCEEDED",
                detail=f"drawdown={slot.max_drawdown_pct:.2%} > limit={self.max_drawdown_pct:.2%}",
            )

        if slot.consecutive_losses > self.max_consecutive_losses:
            return KillReason(
                strategy_id=slot.strategy_id,
                reason="CONSECUTIVE_LOSSES",
                detail=f"losses={slot.consecutive_losses} > limit={self.max_consecutive_losses}",
            )

        if slot.regime_fit_score < self.min_regime_fit and slot.ticks_alive > 50:
            return KillReason(
                strategy_id=slot.strategy_id,
                reason="REGIME_UNFIT",
                detail=f"regime_fit={slot.regime_fit_score:.2f} < min={self.min_regime_fit:.2f}",
            )

        if slot.ticks_alive > 100 and slot.sharpe_ratio < self.min_sharpe_after_incubation:
            return KillReason(
                strategy_id=slot.strategy_id,
                reason="NEGATIVE_SHARPE",
                detail=(
                    f"sharpe={slot.sharpe_ratio:.2f} < min={self.min_sharpe_after_incubation:.2f}"
                ),
            )

        return None

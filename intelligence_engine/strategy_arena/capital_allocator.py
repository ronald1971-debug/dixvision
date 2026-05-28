"""CapitalAllocator — maps arena scores to actual position sizing.

Bridges the arena's abstract allocation percentages to concrete capital
amounts that the execution engine can consume.
"""

from __future__ import annotations

from dataclasses import dataclass

from intelligence_engine.strategy_arena.arena_engine import ArenaEngine, StrategyState


@dataclass(frozen=True, slots=True)
class AllocationDirective:
    """Concrete capital allocation for one strategy."""

    strategy_id: str
    allocation_pct: float
    notional_usd: float
    max_position_usd: float
    risk_budget_pct: float


class CapitalAllocator:
    """Converts arena scores into concrete capital directives.

    Pure function of (arena_state, total_capital, risk_budget).
    No IO, no clocks — deterministic (INV-15).
    """

    def __init__(
        self,
        arena: ArenaEngine,
        *,
        max_single_strategy_risk_pct: float = 0.05,
        scaling_leverage: float = 1.0,
    ) -> None:
        self._arena = arena
        self._max_risk_pct = max_single_strategy_risk_pct
        self._leverage = scaling_leverage

    def allocate(self, total_capital_usd: float) -> list[AllocationDirective]:
        """Generate allocation directives for all active strategies."""
        directives: list[AllocationDirective] = []
        for slot in self._arena.active_slots:
            if slot.state == StrategyState.KILLED:
                continue

            notional = total_capital_usd * slot.allocation_pct * self._leverage
            # Risk budget scales with composite score
            risk_budget = min(
                slot.allocation_pct * slot.composite_score,
                self._max_risk_pct,
            )
            directives.append(
                AllocationDirective(
                    strategy_id=slot.strategy_id,
                    allocation_pct=slot.allocation_pct,
                    notional_usd=notional,
                    max_position_usd=notional * 0.5,  # max 50% in single position
                    risk_budget_pct=risk_budget,
                )
            )
        return directives

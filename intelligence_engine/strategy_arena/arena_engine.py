"""ArenaEngine — Darwinian strategy competition core.

Strategies compete for capital allocation. The arena is deterministic
(INV-15): same sequence of performance updates → same allocation state.
No IO, no clocks, no randomness — pure functional transform.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class StrategyState(StrEnum):
    """Lifecycle of a strategy within the arena."""

    INCUBATING = "INCUBATING"  # new, small allocation, under observation
    SCALING = "SCALING"  # winner, allocation increasing
    STABLE = "STABLE"  # consistent, allocation maintained
    DECAYING = "DECAYING"  # underperforming, allocation shrinking
    KILLED = "KILLED"  # removed from competition


@dataclass(frozen=True, slots=True)
class ArenaConfig:
    """Arena hyperparameters."""

    initial_allocation_pct: float = 0.01  # 1% per new strategy
    max_allocation_pct: float = 0.25  # no single strategy > 25%
    min_allocation_pct: float = 0.001  # below this = killed
    scaling_rate: float = 0.05  # how fast winners grow
    decay_rate: float = 0.10  # how fast losers shrink
    incubation_ticks: int = 100  # minimum observation period
    max_strategies: int = 50  # arena capacity


@dataclass(slots=True)
class StrategySlot:
    """A single strategy competing in the arena."""

    strategy_id: str
    archetype_id: str
    state: StrategyState = StrategyState.INCUBATING
    allocation_pct: float = 0.01
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    regime_fit_score: float = 0.5
    ticks_alive: int = 0
    consecutive_losses: int = 0

    @property
    def composite_score(self) -> float:
        """Weighted composite for ranking."""
        return (
            self.sharpe_ratio * 0.35
            + (1.0 - self.max_drawdown_pct) * 0.25
            + self.win_rate * 0.20
            + self.regime_fit_score * 0.20
        )


class ArenaEngine:
    """Deterministic strategy competition engine.

    On each tick:
    1. Update performance metrics for all active slots.
    2. Transition states based on composite scores.
    3. Reallocate capital proportionally to scores.
    4. Kill strategies below minimum threshold.
    """

    def __init__(self, config: ArenaConfig | None = None) -> None:
        self._config = config or ArenaConfig()
        self._slots: dict[str, StrategySlot] = {}

    @property
    def config(self) -> ArenaConfig:
        return self._config

    @property
    def active_slots(self) -> list[StrategySlot]:
        """All non-killed strategies."""
        return [s for s in self._slots.values() if s.state != StrategyState.KILLED]

    @property
    def allocation_map(self) -> dict[str, float]:
        """Current capital allocation percentages."""
        return {s.strategy_id: s.allocation_pct for s in self.active_slots}

    def admit(self, strategy_id: str, archetype_id: str) -> StrategySlot:
        """Admit a new strategy to the arena."""
        if len(self.active_slots) >= self._config.max_strategies:
            raise ValueError("arena_full")
        if strategy_id in self._slots:
            raise ValueError(f"duplicate_strategy:{strategy_id}")
        slot = StrategySlot(
            strategy_id=strategy_id,
            archetype_id=archetype_id,
            allocation_pct=self._config.initial_allocation_pct,
        )
        self._slots[strategy_id] = slot
        return slot

    def update_performance(
        self,
        strategy_id: str,
        *,
        pnl_delta: float = 0.0,
        win: bool | None = None,
        drawdown_pct: float | None = None,
        regime_fit: float | None = None,
    ) -> StrategySlot:
        """Update a strategy's performance metrics."""
        slot = self._slots.get(strategy_id)
        if slot is None:
            raise LookupError(f"unknown_strategy:{strategy_id}")
        if slot.state == StrategyState.KILLED:
            raise ValueError(f"strategy_killed:{strategy_id}")

        slot.total_pnl += pnl_delta
        slot.ticks_alive += 1

        if win is not None:
            # Exponential moving average of win rate
            alpha = 2.0 / (min(slot.ticks_alive, 50) + 1)
            slot.win_rate = slot.win_rate * (1 - alpha) + (1.0 if win else 0.0) * alpha
            if not win:
                slot.consecutive_losses += 1
            else:
                slot.consecutive_losses = 0

        if drawdown_pct is not None:
            slot.max_drawdown_pct = max(slot.max_drawdown_pct, drawdown_pct)

        if regime_fit is not None:
            slot.regime_fit_score = regime_fit

        # Update Sharpe approximation (simplified — rolling PnL / vol)
        if slot.ticks_alive > 1:
            avg_pnl = slot.total_pnl / slot.ticks_alive
            # Simplified Sharpe: total_pnl / ticks as proxy
            slot.sharpe_ratio = avg_pnl * 100  # scale factor

        return slot

    def tick(self, *, ts_ns: int = 0) -> list[StrategySlot]:
        """Run one arena cycle: transition states + reallocate capital.

        Args:
            ts_ns: Optional caller-supplied timestamp for cognitive
                observability events. Defaults to 0 (no emission) when
                not provided for backward-compatibility.

        Returns list of strategies that were killed this tick.
        """
        killed: list[StrategySlot] = []
        active = self.active_slots
        # Capture pre-tick composite scores for ArchetypeEvolutionEvent emission.
        pre_scores: dict[str, float] = {s.strategy_id: s.composite_score for s in active}

        if not active:
            return killed

        # Phase 1: state transitions
        for slot in active:
            if slot.state == StrategyState.INCUBATING:
                if slot.ticks_alive >= self._config.incubation_ticks:
                    slot.state = (
                        StrategyState.SCALING
                        if slot.composite_score > 0.5
                        else StrategyState.DECAYING
                    )
            elif slot.state in (StrategyState.SCALING, StrategyState.STABLE):
                if slot.composite_score < 0.3:
                    slot.state = StrategyState.DECAYING
                elif slot.composite_score > 0.6:
                    slot.state = StrategyState.SCALING
                else:
                    slot.state = StrategyState.STABLE
            elif slot.state == StrategyState.DECAYING:
                if slot.composite_score > 0.5:
                    slot.state = StrategyState.STABLE
                elif slot.allocation_pct < self._config.min_allocation_pct:
                    slot.state = StrategyState.KILLED
                    killed.append(slot)

        # Phase 2: reallocate capital
        alive = [s for s in active if s.state != StrategyState.KILLED]
        if alive:
            total_score = sum(max(s.composite_score, 0.01) for s in alive)
            for slot in alive:
                target = max(slot.composite_score, 0.01) / total_score
                target = min(target, self._config.max_allocation_pct)
                # Smooth transition
                if slot.state == StrategyState.SCALING:
                    slot.allocation_pct += (
                        target - slot.allocation_pct
                    ) * self._config.scaling_rate
                elif slot.state == StrategyState.DECAYING:
                    slot.allocation_pct -= slot.allocation_pct * self._config.decay_rate
                else:
                    slot.allocation_pct += (target - slot.allocation_pct) * 0.02

            # Normalize to sum=1
            total_alloc = sum(s.allocation_pct for s in alive)
            if total_alloc > 0:
                for slot in alive:
                    slot.allocation_pct /= total_alloc

        if ts_ns > 0:
            self._emit_archetype_events(ts_ns, pre_scores)
        return killed

    def _emit_archetype_events(
        self, ts_ns: int, pre_scores: dict[str, float]
    ) -> None:
        """Best-effort ArchetypeEvolutionEvent emission. Never raises."""
        try:
            from intelligence_engine.cognitive.observability_emitter import (
                emit_archetype_evolution,
            )
            for slot in self.active_slots:
                old = pre_scores.get(slot.strategy_id)
                new = slot.composite_score
                emit_archetype_evolution(
                    ts_ns=ts_ns,
                    archetype_id=slot.archetype_id,
                    archetype_name=slot.archetype_id,
                    old_fitness=old,
                    new_fitness=new,
                    regime=slot.state.value,
                    evaluation_basis="arena_composite_score",
                )
        except Exception:  # pragma: no cover
            pass

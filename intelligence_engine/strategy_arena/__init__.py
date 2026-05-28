"""Strategy Arena — Darwinian capital competition between strategies.

Core principle: every strategy is a living entity competing for capital.
Winners scale, losers decay and die. Capital allocation IS the intelligence.

Flow:
  Indira generates/imports strategies → each enters arena with small allocation
  → performance tracked real-time (Sharpe, drawdown, latency, regime fit)
  → capital reallocates dynamically: winners scale, losers decay → killed.
"""

from intelligence_engine.strategy_arena.arena_engine import (
    ArenaConfig,
    ArenaEngine,
    StrategySlot,
)
from intelligence_engine.strategy_arena.capital_allocator import CapitalAllocator
from intelligence_engine.strategy_arena.kill_underperformers import KillPolicy
from intelligence_engine.strategy_arena.performance_tracker import PerformanceTracker

__all__ = [
    "ArenaEngine",
    "ArenaConfig",
    "StrategySlot",
    "CapitalAllocator",
    "PerformanceTracker",
    "KillPolicy",
]

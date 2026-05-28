"""state.memory_tensor.trader_patterns — Trader pattern store (BUILD-DIRECTIVE §19).

SQLite-backed stores for:
- Trader philosophies and their evolution over time
- Strategy performance per regime
- Pattern frequency and decay curves

This package also exports the TI persistence layer (profile, atom, archetype
stores) added in DIX v42.2.
"""

from __future__ import annotations

from state.memory_tensor.trader_patterns.archetype_store import Archetype, ArchetypeStore
from state.memory_tensor.trader_patterns.atom_store import StrategyAtom, StrategyAtomStore
from state.memory_tensor.trader_patterns.profile_store import TraderProfile, TraderProfileStore

__all__ = (
    "TraderProfile",
    "TraderProfileStore",
    "StrategyAtom",
    "StrategyAtomStore",
    "Archetype",
    "ArchetypeStore",
)

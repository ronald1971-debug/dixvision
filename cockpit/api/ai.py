"""Cockpit API — /ai endpoint.

Returns AI cognitive state: regime, confidence, memory usage,
active hypotheses. Read-only. B1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["AIStateSnapshot", "AIStateProvider"]


@dataclass(frozen=True, slots=True)
class HypothesisSummary:
    id: str
    description: str
    confidence: float
    age_ticks: int


@dataclass(frozen=True, slots=True)
class AIStateSnapshot:
    ts_ns: int
    regime: str
    regime_confidence: float
    hidden_state: str
    memory_utilisation_pct: float
    active_hypotheses: tuple[HypothesisSummary, ...]
    overconfidence_flag: bool


class AIStateProvider:
    """Assembles AIStateSnapshot from intelligence engine state."""

    def __init__(self, intelligence_state: Any, memory_store: Any) -> None:
        self._intel = intelligence_state
        self._memory = memory_store

    def get_snapshot(self, ts_ns: int) -> AIStateSnapshot:
        intel = self._intel.current()
        mem_util = self._memory.utilisation_pct()
        hypotheses = tuple(
            HypothesisSummary(
                id=h.id, description=h.description,
                confidence=h.confidence, age_ticks=h.age_ticks,
            )
            for h in intel.active_hypotheses[:10]
        )
        return AIStateSnapshot(
            ts_ns=ts_ns,
            regime=intel.regime,
            regime_confidence=intel.regime_confidence,
            hidden_state=intel.hidden_state,
            memory_utilisation_pct=mem_util,
            active_hypotheses=hypotheses,
            overconfidence_flag=intel.overconfidence_flag,
        )

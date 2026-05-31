"""cognitive_governance.cognitive_maturity — Manifest §7 maturity model.

Stages 0–8; promotion requires sequential advance and governance approval
for stages ≥ 6.
"""

from __future__ import annotations

import logging
import threading
from enum import IntEnum
from typing import Any

_logger = logging.getLogger(__name__)


class MaturityStage(IntEnum):
    STATIC_ARCHITECTURE = 0
    OBSERVATION = 1
    KNOWLEDGE_FORMATION = 2
    BELIEF_SYSTEMS = 3
    HYPOTHESIS_GENERATION = 4
    CONTINUOUS_LEARNING = 5
    EVOLUTION_PROPOSALS = 6
    GOVERNED_SELF_IMPROVEMENT = 7
    COGNITIVE_OPERATING_SYSTEM = 8


_STAGE_NAMES: dict[int, str] = {int(s): s.name for s in MaturityStage}


class CognitiveMaturityRegistry:
    """Tracks system cognitive maturity; enforces no stage skips."""

    __slots__ = ("_lock", "_stage", "_history")

    def __init__(self, *, initial: MaturityStage = MaturityStage.STATIC_ARCHITECTURE) -> None:
        self._lock = threading.Lock()
        self._stage = initial
        self._history: list[dict[str, Any]] = []

    @property
    def stage(self) -> MaturityStage:
        return self._stage

    def propose_advance(
        self,
        *,
        target: MaturityStage,
        ts_ns: int,
        governance_approved: bool = False,
    ) -> dict[str, Any]:
        """Request promotion to *target*. Returns verdict dict."""
        with self._lock:
            current = int(self._stage)
            target_i = int(target)
            if target_i <= current:
                return {
                    "approved": False,
                    "reason": "not_a_promotion",
                    "current": current,
                    "target": target_i,
                }
            if target_i != current + 1:
                return {
                    "approved": False,
                    "reason": "stage_skip_forbidden",
                    "current": current,
                    "target": target_i,
                }
            if target_i >= int(MaturityStage.EVOLUTION_PROPOSALS) and not governance_approved:
                return {
                    "approved": False,
                    "reason": "governance_approval_required",
                    "current": current,
                    "target": target_i,
                }
            self._stage = target
            record = {
                "from": current,
                "to": target_i,
                "ts_ns": ts_ns,
                "governance_approved": governance_approved,
            }
            self._history.append(record)
            _logger.info(
                "CognitiveMaturityRegistry: %s → %s",
                _STAGE_NAMES[current],
                _STAGE_NAMES[target_i],
            )
            return {"approved": True, **record}

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "stage": int(self._stage),
                "stage_name": self._stage.name,
                "history_len": len(self._history),
                "history_tail": self._history[-5:],
                "max_stage": int(MaturityStage.COGNITIVE_OPERATING_SYSTEM),
            }


_registry: CognitiveMaturityRegistry | None = None
_registry_lock = threading.Lock()


def get_cognitive_maturity_registry() -> CognitiveMaturityRegistry:
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = CognitiveMaturityRegistry()
    return _registry


__all__ = [
    "MaturityStage",
    "CognitiveMaturityRegistry",
    "get_cognitive_maturity_registry",
]

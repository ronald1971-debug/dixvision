"""intelligence_engine.cognitive.cognitive_development_pipeline — Manifest §6 FSM.

Sequential cognitive lifecycle; stages cannot be skipped. Each ``tick()``
advances at most one stage when the current stage's work flag is set.

Authority (B1): intelligence_engine.*, core.*, state.ledger (append only).
"""

from __future__ import annotations

import logging
import threading
from enum import StrEnum
from typing import Any

_logger = logging.getLogger(__name__)


class CognitiveStage(StrEnum):
    OBSERVATION = "OBSERVATION"
    KNOWLEDGE_ACQUISITION = "KNOWLEDGE_ACQUISITION"
    KNOWLEDGE_VALIDATION = "KNOWLEDGE_VALIDATION"
    BELIEF_FORMATION = "BELIEF_FORMATION"
    HYPOTHESIS_GENERATION = "HYPOTHESIS_GENERATION"
    SIMULATION = "SIMULATION"
    EVALUATION = "EVALUATION"
    LEARNING = "LEARNING"
    KNOWLEDGE_UPDATE = "KNOWLEDGE_UPDATE"
    EVOLUTION_PROPOSAL = "EVOLUTION_PROPOSAL"
    GOVERNANCE_REVIEW = "GOVERNANCE_REVIEW"
    APPROVED_COGNITIVE_UPDATE = "APPROVED_COGNITIVE_UPDATE"


_STAGE_ORDER: tuple[CognitiveStage, ...] = tuple(CognitiveStage)


class CognitiveDevelopmentPipeline:
    """Manifest §6 — primary cognitive runtime pipeline."""

    __slots__ = (
        "_lock",
        "_stage",
        "_stage_index",
        "_tick_seq",
        "_stage_ticks",
        "_last_ts_ns",
    )

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stage = CognitiveStage.OBSERVATION
        self._stage_index = 0
        self._tick_seq = 0
        self._stage_ticks: dict[str, int] = {s.value: 0 for s in CognitiveStage}
        self._last_ts_ns = 0

    @property
    def stage(self) -> CognitiveStage:
        return self._stage

    def tick(self, *, ts_ns: int, observation_ready: bool = True) -> dict[str, Any]:
        """Advance the pipeline by at most one stage per call."""
        with self._lock:
            self._tick_seq += 1
            self._last_ts_ns = ts_ns
            self._stage_ticks[self._stage.value] += 1
            current = self._stage
            advanced = False

            if observation_ready and self._stage_index < len(_STAGE_ORDER) - 1:
                self._stage_index += 1
                self._stage = _STAGE_ORDER[self._stage_index]
                advanced = True
                _logger.debug(
                    "CognitiveDevelopmentPipeline: %s → %s",
                    current.value,
                    self._stage.value,
                )

            return {
                "tick_seq": self._tick_seq,
                "stage": self._stage.value,
                "previous_stage": current.value,
                "advanced": advanced,
                "stage_index": self._stage_index,
                "ts_ns": ts_ns,
            }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "pipeline": "CognitiveDevelopmentPipeline",
                "stage": self._stage.value,
                "stage_index": self._stage_index,
                "tick_seq": self._tick_seq,
                "stage_ticks": dict(self._stage_ticks),
                "last_ts_ns": self._last_ts_ns,
                "stages": [s.value for s in _STAGE_ORDER],
            }


_pipeline: CognitiveDevelopmentPipeline | None = None
_pipeline_lock = threading.Lock()


def get_cognitive_development_pipeline() -> CognitiveDevelopmentPipeline:
    global _pipeline
    with _pipeline_lock:
        if _pipeline is None:
            _pipeline = CognitiveDevelopmentPipeline()
    return _pipeline


__all__ = [
    "CognitiveStage",
    "CognitiveDevelopmentPipeline",
    "get_cognitive_development_pipeline",
]

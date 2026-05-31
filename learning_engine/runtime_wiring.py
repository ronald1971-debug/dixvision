"""learning_engine.runtime_wiring — Tier-2 learning feedback loop wiring.

Ensures execution outcomes reach learning consumers and governed market
context reaches INDIRA learning persistence.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LearningWiringResult:
    closed_loop_wired: bool
    feedback_collector_wired: bool
    governed_context_wired: bool
    patch_outcome_wired: bool
    detail: str = ""


def wire_learning_runtime(state: Any | None = None) -> LearningWiringResult:
    """Wire learning feedback paths (idempotent)."""
    closed_loop_wired = False
    feedback_collector_wired = False
    governed_context_wired = False
    patch_outcome_wired = False

    if state is not None:
        loop = getattr(state, "closed_learning_loop", None)
        collector = getattr(state, "feedback_collector", None)
        closed_loop_wired = loop is not None
        feedback_collector_wired = collector is not None
        patch_outcome_wired = getattr(state, "patch_outcome_feedback", None) is not None

    try:
        from governance.market_context_projector import get_market_context_projector
        from intelligence_engine.cognitive.dyon_signal_bridge import get_dyon_signal_bridge

        get_market_context_projector().activate()
        get_dyon_signal_bridge().activate()
        governed_context_wired = True
    except Exception as exc:
        _logger.debug("runtime_wiring: governed context: %s", exc)

    if state is not None and feedback_collector_wired:
        _wire_execution_feedback_sink(state)

    detail = (
        f"closed_loop={closed_loop_wired} collector={feedback_collector_wired} "
        f"governed={governed_context_wired} patch_outcome={patch_outcome_wired}"
    )
    _logger.info("learning_engine.runtime_wiring: %s", detail)
    return LearningWiringResult(
        closed_loop_wired=closed_loop_wired,
        feedback_collector_wired=feedback_collector_wired,
        governed_context_wired=governed_context_wired,
        patch_outcome_wired=patch_outcome_wired,
        detail=detail,
    )


def _wire_execution_feedback_sink(state: Any) -> None:
    """Attach FeedbackCollector → LearningInterface when STATE provides both."""
    collector = getattr(state, "feedback_collector", None)
    interface = getattr(state, "learning_interface", None)
    engine = getattr(state, "execution_engine", None)
    if collector is None or interface is None or engine is None:
        return
    try:
        if getattr(engine, "_feedback_collector", None) is collector:
            return
        if hasattr(engine, "set_feedback_sinks"):
            engine.set_feedback_sinks(
                feedback_collector=collector,
                intelligence_sink=interface,
            )
        else:
            engine._feedback_collector = collector  # type: ignore[attr-defined]
            engine._intelligence_sink = interface  # type: ignore[attr-defined]
        _logger.info("learning_engine.runtime_wiring: execution feedback sinks attached")
    except Exception as exc:
        _logger.debug("runtime_wiring: execution sink attach: %s", exc)


def learning_is_active(state: Any | None = None) -> bool:
    """Health probe: True when closed loop exists and is not frozen."""
    if state is None:
        return False
    loop = getattr(state, "closed_learning_loop", None)
    if loop is None:
        return False
    supplier = getattr(loop, "_policy_supplier", None)
    if supplier is None:
        return True
    try:
        policy = supplier()
        return policy is None or not getattr(policy, "frozen", False)
    except Exception:
        return False


__all__ = [
    "LearningWiringResult",
    "learning_is_active",
    "wire_learning_runtime",
]

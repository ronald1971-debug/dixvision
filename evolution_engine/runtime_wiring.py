"""evolution_engine.runtime_wiring — Tier-2 evolution engine wiring.

Connects EvolutionOrchestrator, GovernedEvolutionPipeline, and optional
server ``STATE`` structural loop so health checks report wired status.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EvolutionWiringResult:
    orchestrator_wired: bool
    governed_pipeline_wired: bool
    structural_loop_wired: bool
    critique_loop_wired: bool
    dyon_engineering_wired: bool
    detail: str = ""


def wire_evolution_runtime(state: Any | None = None) -> EvolutionWiringResult:
    """Wire evolution subsystems at boot (idempotent)."""
    orchestrator_wired = False
    governed_pipeline_wired = False
    structural_loop_wired = False
    critique_loop_wired = False
    dyon_engineering_wired = False

    try:
        from evolution_engine.evolution_orchestrator import get_evolution_orchestrator

        evo = get_evolution_orchestrator()
        orchestrator_wired = True

        if state is not None:
            loop = getattr(state, "structural_evolution_loop", None)
            if loop is not None:
                evo.register_structural_loop(loop)
                structural_loop_wired = True
            critique = getattr(state, "critique_loop", None)
            if critique is not None:
                evo.register_critique_loop(critique)
                critique_loop_wired = True

        snap = evo.snapshot()
        structural_loop_wired = structural_loop_wired or bool(snap.get("structural_loop_wired"))
        critique_loop_wired = critique_loop_wired or bool(snap.get("critique_loop_wired"))
    except Exception as exc:
        _logger.debug("runtime_wiring: evolution orchestrator: %s", exc)

    try:
        from evolution_engine.governed_pipeline import get_governed_pipeline

        pipe = get_governed_pipeline()
        if hasattr(pipe, "activate"):
            pipe.activate()
        governed_pipeline_wired = True
    except Exception as exc:
        _logger.debug("runtime_wiring: governed pipeline: %s", exc)

    try:
        from evolution_engine.dyon.dyon_engineering_runtime import get_dyon_engineering_runtime

        eng = get_dyon_engineering_runtime()
        if hasattr(eng, "activate"):
            eng.activate()
        dyon_engineering_wired = True
    except Exception as exc:
        _logger.debug("runtime_wiring: dyon engineering: %s", exc)

    detail = (
        f"orchestrator={orchestrator_wired} pipeline={governed_pipeline_wired} "
        f"structural={structural_loop_wired} critique={critique_loop_wired}"
    )
    _logger.info("evolution_engine.runtime_wiring: %s", detail)
    return EvolutionWiringResult(
        orchestrator_wired=orchestrator_wired,
        governed_pipeline_wired=governed_pipeline_wired,
        structural_loop_wired=structural_loop_wired,
        critique_loop_wired=critique_loop_wired,
        dyon_engineering_wired=dyon_engineering_wired,
        detail=detail,
    )


def evolution_is_active(state: Any | None = None) -> bool:
    """Health probe: True when structural loop exists and is not frozen."""
    if state is None:
        return False
    loop = getattr(state, "structural_evolution_loop", None)
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
    "EvolutionWiringResult",
    "evolution_is_active",
    "wire_evolution_runtime",
]

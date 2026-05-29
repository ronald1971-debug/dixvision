"""EvolutionOrchestrator — unified evolution coordinator (CONSOLIDATION PHASE).

Single entry point over all evolution subsystems:

    DyonRuntime          — topology scanning → architectural patch proposals
    StructuralLoop       — genetic algorithm driver (requires policy supplier)
    PatchPipeline        — propose → sandbox → analyse → backtest → canary
    CritiqueLoop         — LLM-backed fitness evaluation
    Arena                — strategy archetype competition

Complex subsystems (StructuralLoop, PatchPipeline) require construction-time
collaborators that are wired at boot; they are injected via register() rather
than lazily imported. Simple subsystems (DyonRuntime, CritiqueLoop) are
lazily imported.

tick(ts_ns) drives one orchestration cycle in the following order:
    1. DyonRuntime.tick()        — topology scan on its own interval
    2. StructuralLoop.tick()     — genetic proposals (if registered)
    3. CritiqueLoop tick         — fitness evaluation (if available)

Authority (L2/B1): imports only from evolution_engine.* and core.*.
Never imports intelligence_engine, execution_engine, or governance_engine
at the module level.
INV-15: ts_ns is caller-supplied; no internal clock reads.
"""

from __future__ import annotations

import logging
from typing import Any

from evolution_engine.dyon.dyon_runtime import DyonRuntime, get_dyon_runtime

_logger = logging.getLogger(__name__)


class EvolutionOrchestrator:
    """Coordinates all evolution subsystems from one tick().

    Args:
        dyon_runtime: DYON topology scanner. Defaults to the singleton.
    """

    def __init__(self, *, dyon_runtime: DyonRuntime | None = None) -> None:
        self._dyon = dyon_runtime or get_dyon_runtime()
        self._structural_loop: Any = None
        self._critique_loop: Any = None
        self._arena: Any = None
        self._tick_count: int = 0

    # ------------------------------------------------------------------
    # Injection — called at boot time once collaborators are wired
    # ------------------------------------------------------------------

    def register_structural_loop(self, loop: Any) -> None:
        """Inject the StructuralEvolutionLoop after boot wiring."""
        self._structural_loop = loop
        _logger.info("EvolutionOrchestrator: structural loop registered")

    def register_critique_loop(self, loop: Any) -> None:
        self._critique_loop = loop
        _logger.info("EvolutionOrchestrator: critique loop registered")

    def register_arena(self, arena: Any) -> None:
        self._arena = arena
        _logger.info("EvolutionOrchestrator: arena registered")

    # ------------------------------------------------------------------
    # Primary tick
    # ------------------------------------------------------------------

    def tick(self, *, ts_ns: int) -> None:
        """Drive one evolution orchestration cycle (best-effort per stage)."""
        self._tick_count += 1

        # Stage 1: DYON topology scan (self-throttled to scan_interval)
        try:
            self._dyon.tick(ts_ns=ts_ns)
        except Exception as exc:
            _logger.debug("EvolutionOrchestrator: dyon tick error: %s", exc)

        # Stage 2: Structural loop (only if injected)
        if self._structural_loop is not None:
            try:
                if hasattr(self._structural_loop, "tick"):
                    self._structural_loop.tick(ts_ns=ts_ns)
            except Exception as exc:
                _logger.debug("EvolutionOrchestrator: structural loop error: %s", exc)

        # Stage 3: Critique loop (only if injected; runs every 100 ticks)
        if self._critique_loop is not None and self._tick_count % 100 == 0:
            try:
                if hasattr(self._critique_loop, "tick"):
                    self._critique_loop.tick(ts_ns=ts_ns)
                elif hasattr(self._critique_loop, "run"):
                    self._critique_loop.run()
            except Exception as exc:
                _logger.debug("EvolutionOrchestrator: critique loop error: %s", exc)

        # Stage 4: Lazy critique loop (auto-wire if not injected, every 500 ticks)
        if self._critique_loop is None and self._tick_count % 500 == 0:
            self._try_auto_wire_critique()

    # ------------------------------------------------------------------
    # Read surface
    # ------------------------------------------------------------------

    def snapshot(self, proposal_limit: int = 20) -> dict[str, Any]:
        """JSON-serialisable snapshot of the evolution pipeline state."""
        return {
            "orchestrator": "EvolutionOrchestrator",
            "tick_count": self._tick_count,
            "dyon": self._dyon.snapshot(proposal_limit),
            "structural_loop_wired": self._structural_loop is not None,
            "critique_loop_wired": self._critique_loop is not None,
            "arena_wired": self._arena is not None,
        }

    @property
    def dyon_runtime(self) -> DyonRuntime:
        return self._dyon

    # ------------------------------------------------------------------
    # Auto-wire helpers (best-effort)
    # ------------------------------------------------------------------

    def _try_auto_wire_critique(self) -> None:
        try:
            from evolution_engine.critique_loop import CritiqueLoop
            self._critique_loop = CritiqueLoop()
            _logger.info("EvolutionOrchestrator: auto-wired CritiqueLoop")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_orchestrator: EvolutionOrchestrator | None = None


def get_evolution_orchestrator() -> EvolutionOrchestrator:
    """Return the module-level singleton EvolutionOrchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = EvolutionOrchestrator(dyon_runtime=get_dyon_runtime())
    return _orchestrator


__all__ = [
    "EvolutionOrchestrator",
    "get_evolution_orchestrator",
]

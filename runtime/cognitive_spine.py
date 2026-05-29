"""runtime.cognitive_spine — Unified Cognitive Orchestration Spine.

THE single driver for all cognitive subsystems.  Every process has exactly
one CognitiveSpine; all cognitive ticks flow through it in a fixed sequence:

  Phase 0 — CognitiveGovernance   integrity gate (self-rate-limits to 60s)
  Phase 1 — MemoryOrchestrator    consolidation pass
  Phase 2 — TraderIntelligence    regime-adjusted archetype evaluation
  Phase 3 — IndiraRuntime         INDIRA market reasoning cycle
  Phase 4 — EvolutionOrchestrator DYON scan + architectural proposals

On activate():
  - CognitiveTelemetry  subscribed to all 8 event bus channels (spans)
  - DyonSignalBridge    subscribed to DYON + risk channels (INDIRA coupling)
  - TraderIntelligence  seeded with 86 historical archetypes

Replaces the duplicate driving in RuntimeBootstrap._tick_loop() phases 5-7
and in CognitionDaemon's separate indira_loop / dyon_loop tasks.

Authority (B1): intelligence_engine.*, evolution_engine.*, state.*, core.* only.
INV-15: ts_ns is always caller-supplied; no wall-clock reads inside phases.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from system import time_source

_logger = logging.getLogger(__name__)


class CognitiveSpine:
    """Sequences all cognitive subsystems in one authoritative tick.

    Args:
        cogov_every: run CognitiveGovernance emit every N ticks (default 1;
            the engine itself rate-limits to 60s so calling every tick is free).
        memory_every: run MemoryOrchestrator consolidation every N ticks.
        trader_every: run TraderIntelligenceRuntime every N ticks.
        indira_every: run IndiraRuntime every N ticks.
        dyon_every: run EvolutionOrchestrator every N ticks.
    """

    __slots__ = (
        "_lock",
        "_active",
        "_tick_seq",
        "_cogov_every",
        "_memory_every",
        "_trader_every",
        "_indira_every",
        "_dyon_every",
        "_phase_errors",
        "_cogov",
        "_memory",
        "_trader",
        "_trader_modeling",
        "_indira",
        "_evolution",
        "_governed_pipeline",
        "_sim_dominance",
        "_dyon_engineering",
    )

    def __init__(
        self,
        *,
        cogov_every: int = 1,
        memory_every: int = 5,
        trader_every: int = 2,
        indira_every: int = 1,
        dyon_every: int = 3,
    ) -> None:
        self._lock = threading.Lock()
        self._active = False
        self._tick_seq = 0
        self._cogov_every = max(1, cogov_every)
        self._memory_every = max(1, memory_every)
        self._trader_every = max(1, trader_every)
        self._indira_every = max(1, indira_every)
        self._dyon_every = max(1, dyon_every)
        self._phase_errors: dict[str, int] = {
            "cogov": 0, "memory": 0, "trader": 0, "indira": 0, "dyon": 0,
        }
        # Lazy singletons (cached after first successful load)
        self._cogov: Any = None
        self._memory: Any = None
        self._trader: Any = None
        self._trader_modeling: Any = None
        self._indira: Any = None
        self._evolution: Any = None
        self._governed_pipeline: Any = None
        self._sim_dominance: Any = None
        self._dyon_engineering: Any = None

    # ------------------------------------------------------------------
    # Activation — idempotent, safe to call from any thread
    # ------------------------------------------------------------------

    def activate(self) -> None:
        """Activate the spine and all cognitive subsystems.

        Must be called once before the first tick().  Idempotent.
        """
        with self._lock:
            if self._active:
                return
            self._active = True

        _logger.info("CognitiveSpine: activating all cognitive subsystems")

        self._activate_telemetry()
        self._activate_signal_bridge()
        self._activate_trader_intelligence()
        self._activate_dyon_engineering()
        self._warm_singletons()

        _logger.info("CognitiveSpine: activated (all subsystems online)")

    # ------------------------------------------------------------------
    # Tick — the authoritative cognitive cycle
    # ------------------------------------------------------------------

    def tick(self, *, ts_ns: int) -> dict[str, bool]:
        """Drive all cognitive subsystems in sequence.

        Returns a dict of phase_name → ran (True if the phase executed
        this tick, False if skipped by its cadence divisor).
        """
        with self._lock:
            if not self._active:
                return {}
            self._tick_seq += 1
            seq = self._tick_seq

        ran: dict[str, bool] = {}

        # Phase 0 — CognitiveGovernance integrity gate
        if seq % self._cogov_every == 0:
            self._run_cogov(ts_ns)
            ran["cogov"] = True
        else:
            ran["cogov"] = False

        # Phase 1 — Memory consolidation
        if seq % self._memory_every == 0:
            self._run_memory(ts_ns)
            ran["memory"] = True
        else:
            ran["memory"] = False

        # Phase 2 — TraderIntelligence (archetype arena + live behavioral profiling)
        if seq % self._trader_every == 0:
            self._run_trader(ts_ns)
            self._run_trader_modeling(ts_ns)
            ran["trader"] = True
        else:
            ran["trader"] = False

        # Phase 3 — INDIRA
        if seq % self._indira_every == 0:
            self._run_indira(ts_ns)
            ran["indira"] = True
        else:
            ran["indira"] = False

        # Phase 4 — DYON / Evolution + governed pipeline + simulation dominance
        if seq % self._dyon_every == 0:
            self._run_dyon_engineering(ts_ns)   # unified DYON identity (drives DyonRuntime internally)
            self._run_governed_pipeline(ts_ns)
            self._run_sim_dominance(ts_ns)
            ran["dyon"] = True
        else:
            ran["dyon"] = False

        return ran

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            seq = self._tick_seq
            active = self._active
            errors = dict(self._phase_errors)

        out: dict[str, Any] = {
            "spine": "CognitiveSpine",
            "active": active,
            "tick_seq": seq,
            "phase_errors": errors,
            "cadence": {
                "cogov_every": self._cogov_every,
                "memory_every": self._memory_every,
                "trader_every": self._trader_every,
                "indira_every": self._indira_every,
                "dyon_every": self._dyon_every,
            },
            "subsystems": {},
        }

        # Collect subsystem snapshots best-effort
        for name, getter in (
            ("memory", self._get_memory),
            ("indira", self._get_indira),
            ("trader", self._get_trader),
            ("dyon", self._get_evolution),
            ("dyon_engineering", self._get_dyon_engineering),
        ):
            try:
                obj = getter()
                if obj is not None and hasattr(obj, "snapshot"):
                    out["subsystems"][name] = obj.snapshot()
            except Exception:
                pass

        return out

    # ------------------------------------------------------------------
    # Phase runners (each is try/except — never raises to caller)
    # ------------------------------------------------------------------

    def _run_cogov(self, ts_ns: int) -> None:
        try:
            obj = self._get_cogov()
            if obj is not None and hasattr(obj, "emit_status"):
                obj.emit_status()
        except Exception as exc:
            self._phase_errors["cogov"] += 1
            _logger.debug("CognitiveSpine.cogov error: %s", exc)

    def _run_memory(self, ts_ns: int) -> None:
        try:
            obj = self._get_memory()
            if obj is not None:
                obj.consolidate(ts_ns=ts_ns)
        except Exception as exc:
            self._phase_errors["memory"] += 1
            _logger.debug("CognitiveSpine.memory error: %s", exc)

    def _run_trader(self, ts_ns: int) -> None:
        try:
            obj = self._get_trader()
            if obj is not None:
                obj.tick(ts_ns=ts_ns)
        except Exception as exc:
            self._phase_errors["trader"] += 1
            _logger.debug("CognitiveSpine.trader error: %s", exc)

    def _run_indira(self, ts_ns: int) -> None:
        try:
            obj = self._get_indira()
            if obj is not None:
                obj.tick(ts_ns=ts_ns)
        except Exception as exc:
            self._phase_errors["indira"] += 1
            _logger.debug("CognitiveSpine.indira error: %s", exc)

    def _run_dyon(self, ts_ns: int) -> None:
        try:
            obj = self._get_evolution()
            if obj is not None:
                obj.tick(ts_ns=ts_ns)
        except Exception as exc:
            self._phase_errors["dyon"] += 1
            _logger.debug("CognitiveSpine.dyon error: %s", exc)

    def _run_dyon_engineering(self, ts_ns: int) -> None:
        """Drive the unified DyonEngineeringRuntime (replaces bare _run_dyon in phase 4)."""
        try:
            obj = self._get_dyon_engineering()
            if obj is not None:
                obj.tick(ts_ns=ts_ns)
            else:
                # Fallback to legacy EvolutionOrchestrator if engineering runtime unavailable
                self._run_dyon(ts_ns)
        except Exception as exc:
            self._phase_errors["dyon"] += 1
            _logger.debug("CognitiveSpine.dyon_engineering error: %s", exc)

    def _run_trader_modeling(self, ts_ns: int) -> None:
        try:
            obj = self._get_trader_modeling()
            if obj is not None:
                obj.tick(ts_ns=ts_ns)
        except Exception as exc:
            _logger.debug("CognitiveSpine.trader_modeling error: %s", exc)

    def _run_governed_pipeline(self, ts_ns: int) -> None:
        try:
            obj = self._get_governed_pipeline()
            if obj is not None:
                obj.tick(ts_ns=ts_ns)
        except Exception as exc:
            _logger.debug("CognitiveSpine.governed_pipeline error: %s", exc)

    def _run_sim_dominance(self, ts_ns: int) -> None:
        try:
            obj = self._get_sim_dominance()
            if obj is not None:
                obj.tick(ts_ns=ts_ns)
        except Exception as exc:
            _logger.debug("CognitiveSpine.sim_dominance error: %s", exc)

    # ------------------------------------------------------------------
    # Activation helpers
    # ------------------------------------------------------------------

    def _activate_telemetry(self) -> None:
        try:
            from state.telemetry.cognitive_telemetry import get_cognitive_telemetry
            get_cognitive_telemetry().activate()
            _logger.info("CognitiveSpine: CognitiveTelemetry activated")
        except Exception as exc:
            _logger.debug("CognitiveSpine: CognitiveTelemetry unavailable: %s", exc)

    def _activate_signal_bridge(self) -> None:
        try:
            from intelligence_engine.cognitive.dyon_signal_bridge import get_dyon_signal_bridge
            get_dyon_signal_bridge().activate()
            _logger.info("CognitiveSpine: DyonSignalBridge activated")
        except Exception as exc:
            _logger.debug("CognitiveSpine: DyonSignalBridge unavailable: %s", exc)

    def _activate_trader_intelligence(self) -> None:
        try:
            from intelligence_engine.cognitive.trader_intelligence_runtime import (
                get_trader_intelligence_runtime,
            )
            get_trader_intelligence_runtime().activate()
            _logger.info("CognitiveSpine: TraderIntelligenceRuntime activated")
        except Exception as exc:
            _logger.debug("CognitiveSpine: TraderIntelligenceRuntime unavailable: %s", exc)
        try:
            from trader_modeling.trader_modeling_runtime import get_trader_modeling_runtime
            get_trader_modeling_runtime().activate()
            _logger.info("CognitiveSpine: TraderModelingRuntime activated (live profiling)")
        except Exception as exc:
            _logger.debug("CognitiveSpine: TraderModelingRuntime unavailable: %s", exc)

    def _warm_singletons(self) -> None:
        """Eagerly load all phase singletons so first tick has no import cost."""
        self._get_cogov()
        self._get_memory()
        self._get_trader()
        self._get_trader_modeling()
        self._get_indira()
        self._get_evolution()
        self._get_governed_pipeline()
        self._get_sim_dominance()
        self._get_dyon_engineering()

    # ------------------------------------------------------------------
    # Lazy singleton accessors
    # ------------------------------------------------------------------

    def _get_cogov(self) -> Any:
        if self._cogov is None:
            try:
                from cognitive_governance.engine import get_cognitive_governance
                self._cogov = get_cognitive_governance()
            except Exception:
                pass
        return self._cogov

    def _get_memory(self) -> Any:
        if self._memory is None:
            try:
                from state.memory_tensor.memory_orchestrator import get_memory_orchestrator
                self._memory = get_memory_orchestrator()
            except Exception:
                pass
        return self._memory

    def _get_trader(self) -> Any:
        if self._trader is None:
            try:
                from intelligence_engine.cognitive.trader_intelligence_runtime import (
                    get_trader_intelligence_runtime,
                )
                self._trader = get_trader_intelligence_runtime()
            except Exception:
                pass
        return self._trader

    def _get_indira(self) -> Any:
        if self._indira is None:
            try:
                from intelligence_engine.cognitive.indira_runtime import get_indira_runtime
                self._indira = get_indira_runtime()
            except Exception:
                pass
        return self._indira

    def _get_evolution(self) -> Any:
        if self._evolution is None:
            try:
                from evolution_engine.evolution_orchestrator import get_evolution_orchestrator
                self._evolution = get_evolution_orchestrator()
            except Exception:
                pass
        return self._evolution

    def _get_trader_modeling(self) -> Any:
        if self._trader_modeling is None:
            try:
                from trader_modeling.trader_modeling_runtime import get_trader_modeling_runtime
                self._trader_modeling = get_trader_modeling_runtime()
            except Exception:
                pass
        return self._trader_modeling

    def _get_governed_pipeline(self) -> Any:
        if self._governed_pipeline is None:
            try:
                from evolution_engine.governed_pipeline import get_governed_pipeline
                self._governed_pipeline = get_governed_pipeline()
            except Exception:
                pass
        return self._governed_pipeline

    def _get_sim_dominance(self) -> Any:
        if self._sim_dominance is None:
            try:
                from simulation.dominance_runtime import get_simulation_dominance_runtime
                self._sim_dominance = get_simulation_dominance_runtime()
            except Exception:
                pass
        return self._sim_dominance

    def _get_dyon_engineering(self) -> Any:
        if self._dyon_engineering is None:
            try:
                from evolution_engine.dyon.dyon_engineering_runtime import (
                    get_dyon_engineering_runtime,
                )
                self._dyon_engineering = get_dyon_engineering_runtime()
            except Exception:
                pass
        return self._dyon_engineering

    def _activate_dyon_engineering(self) -> None:
        try:
            obj = self._get_dyon_engineering()
            if obj is not None:
                obj.activate()
                _logger.info("CognitiveSpine: DyonEngineeringRuntime activated")
        except Exception as exc:
            _logger.debug("CognitiveSpine: DyonEngineeringRuntime unavailable: %s", exc)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_spine: CognitiveSpine | None = None
_spine_lock = threading.Lock()


def get_cognitive_spine() -> CognitiveSpine:
    """Return the process-wide CognitiveSpine singleton."""
    global _spine
    with _spine_lock:
        if _spine is None:
            _spine = CognitiveSpine()
    return _spine


__all__ = [
    "CognitiveSpine",
    "get_cognitive_spine",
]

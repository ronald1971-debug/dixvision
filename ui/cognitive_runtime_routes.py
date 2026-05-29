"""ui.cognitive_runtime_routes — Unified Cognitive Runtime Kernel REST surfaces.

Operator visibility into the UnifiedCognitiveKernel — the nervous system
connecting all cognitive, memory, governance, and telemetry subsystems.

Routes (all under /api/runtime/cognitive/):
  GET /kernel     — UnifiedCognitiveKernel status + components
  GET /state      — full unified system state (all subsystems)
  GET /health     — per-subsystem health scores
  GET /telemetry  — event throughput + gauge metrics
  GET /scheduler  — CognitionScheduler urgency plan
  GET /memory     — MemoryCoordinator capture counts
  GET /routes     — CrossBusRouter routing stats
  GET /governance — GovernanceRouter routing stats
"""

from __future__ import annotations

import importlib
from typing import Any

from fastapi import APIRouter

from system.time_source import utc_now, wall_ns


def build_cognitive_runtime_router() -> APIRouter:
    """Construct the cognitive runtime API router."""

    router = APIRouter(prefix="/api/runtime/cognitive", tags=["cognitive-runtime"])

    # ------------------------------------------------------------------
    # Kernel — top-level unified kernel status
    # ------------------------------------------------------------------

    @router.get("/kernel")
    def cognitive_kernel() -> dict[str, Any]:
        """UnifiedCognitiveKernel: all infrastructure components + tick count."""
        try:
            from runtime.unified_kernel import get_unified_kernel
            return {"ts_iso": utc_now().isoformat(), **get_unified_kernel().snapshot()}
        except Exception as exc:
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # State — full unified system state
    # ------------------------------------------------------------------

    @router.get("/state")
    def cognitive_state() -> dict[str, Any]:
        """Unified system state — all subsystems in one response.

        Aggregates: market, risk, indira, dyon, evolution, simulation,
        memory, governance, spine.
        """
        ts_ns = wall_ns()
        try:
            from state.state_sync import get_state_sync
            return {"ts_iso": utc_now().isoformat(), **get_state_sync().snapshot(ts_ns=ts_ns)}
        except Exception as exc:
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Health — per-subsystem health scores
    # ------------------------------------------------------------------

    @router.get("/health")
    def cognitive_health() -> dict[str, Any]:
        """Per-subsystem health scores for the operator dashboard."""
        ts_iso = utc_now().isoformat()
        health: dict[str, Any] = {"ts_iso": ts_iso, "subsystems": {}}

        checks = {
            "unified_kernel":        ("runtime.unified_kernel", "get_unified_kernel"),
            "cognitive_spine":       ("runtime.cognitive_spine", "get_cognitive_spine"),
            "cognition_daemon":      ("runtime.cognition_daemon", "get_cognition_daemon"),
            "event_bus":             ("state.event_bus", "get_event_bus"),
            "memory_orchestrator":   ("state.memory_tensor.memory_orchestrator",
                                      "get_memory_orchestrator"),
            "indira_runtime":        ("intelligence_engine.cognitive.indira_runtime",
                                      "get_indira_runtime"),
            "evolution_orchestrator":("evolution_engine.evolution_orchestrator",
                                      "get_evolution_orchestrator"),
            "risk_tracker":          ("governance_engine.risk_engine.risk_tracker",
                                      "get_risk_tracker"),
        }

        for name, (module, factory) in checks.items():
            try:
                mod = importlib.import_module(module)
                obj = getattr(mod, factory)()
                snap = obj.snapshot() if hasattr(obj, "snapshot") else {}
                health["subsystems"][name] = {
                    "online": True,
                    "tick_count": snap.get("tick_count", snap.get("tick_seq")),
                    "error_count": snap.get("error_count"),
                }
            except Exception as exc:
                health["subsystems"][name] = {"online": False, "error": str(exc)[:80]}

        online = sum(1 for v in health["subsystems"].values() if v.get("online"))
        total = len(checks)
        health["health_score"] = round(online / total, 2) if total else 0.0
        health["online"] = online
        health["total"] = total
        return health

    # ------------------------------------------------------------------
    # Telemetry — event throughput + gauge metrics
    # ------------------------------------------------------------------

    @router.get("/telemetry")
    def cognitive_telemetry_agg() -> dict[str, Any]:
        """Unified telemetry: event throughput/min + subsystem gauges."""
        try:
            from runtime.telemetry_aggregator import get_telemetry_aggregator
            return {"ts_iso": utc_now().isoformat(), **get_telemetry_aggregator().summary()}
        except Exception as exc:
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Scheduler — urgency plan + active boosts
    # ------------------------------------------------------------------

    @router.get("/scheduler")
    def cognitive_scheduler() -> dict[str, Any]:
        """CognitionScheduler: active urgency boosts + recent signal log."""
        try:
            from runtime.cognition_scheduler import get_cognition_scheduler
            return {"ts_iso": utc_now().isoformat(), **get_cognition_scheduler().snapshot()}
        except Exception as exc:
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Memory coordinator — capture counts
    # ------------------------------------------------------------------

    @router.get("/memory")
    def cognitive_memory_coord() -> dict[str, Any]:
        """MemoryCoordinator: auto-capture counts (episodic/semantic/procedural/errors)."""
        try:
            from runtime.memory_coordinator import get_memory_coordinator
            return {"ts_iso": utc_now().isoformat(), **get_memory_coordinator().snapshot()}
        except Exception as exc:
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Cross-bus router — routing stats
    # ------------------------------------------------------------------

    @router.get("/routes")
    def cognitive_routes() -> dict[str, Any]:
        """CrossBusRouter: events routed between cognitive bus and execution fabric."""
        try:
            from runtime.cross_bus_router import get_cross_bus_router
            return {"ts_iso": utc_now().isoformat(), **get_cross_bus_router().snapshot()}
        except Exception as exc:
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Governance router
    # ------------------------------------------------------------------

    @router.get("/governance")
    def cognitive_governance_route() -> dict[str, Any]:
        """GovernanceRouter: mode transitions and cogov violations routed to cognition."""
        try:
            from runtime.governance_router import get_governance_router
            return {"ts_iso": utc_now().isoformat(), **get_governance_router().snapshot()}
        except Exception as exc:
            return {"error": str(exc)}

    return router


__all__ = ["build_cognitive_runtime_router"]

"""runtime.unified_kernel — Unified Cognitive Runtime Kernel.

THE nervous system of DixVision.

Integrates all cognitive, memory, governance, and telemetry subsystems
into one coherent runtime kernel.  Every active component of the system
is wired through this kernel.

Architecture:
  CognitiveSpine        — sequenced 5-phase cognitive executor
  CognitionScheduler    — urgency-aware dynamic tick planner
  MemoryCoordinator     — auto-captures cognitive events to memory
  TelemetryAggregator   — unified metrics from all subsystems
  CrossBusRouter        — bridges cognitive bus ↔ execution fabric
  GovernanceRouter      — routes governance decisions to INDIRA/DYON
  UnifiedStateSync      — full-system state snapshot

Boot sequence (activate()):
  1. CrossBusRouter      — wire event bridges first
  2. GovernanceRouter    — governance routing before any ticks
  3. CognitionScheduler  — urgency tracking before cognitive loop
  4. MemoryCoordinator   — memory capture before first thought
  5. TelemetryAggregator — metrics collection before first poll
  6. CognitiveSpine      — start cognitive loop (INDIRA + DYON live)

Tick sequence (tick(ts_ns)):
  1. scheduler.plan()       — compute dynamic schedule
  2. spine.tick()           — drive all cognitive phases
  3. telemetry.poll()       — sample gauges from all singletons

Operator interface:
  kernel.snapshot()        — full unified system view
  kernel.state_snapshot()  — all subsystem states in one call
  GET /api/runtime/*       — REST surfaces

Authority: runtime tier. Never imports execution_engine.hot_path.
INV-15: ts_ns caller-supplied throughout.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tick result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class KernelTickResult:
    """Outcome of one unified kernel tick."""

    tick_seq: int
    ts_ns: int
    phases_ran: dict[str, bool]
    urgent_phases: list[str]
    errors: int


# ---------------------------------------------------------------------------
# UnifiedCognitiveKernel
# ---------------------------------------------------------------------------


class UnifiedCognitiveKernel:
    """The nervous system of DixVision.

    Owns all cognitive infrastructure components.  The CognitionDaemon
    holds one instance of this kernel and drives it on a 2-second cadence.
    """

    __slots__ = (
        "_lock",
        "_active",
        "_tick_seq",
        "_error_count",
        "_scheduler",
        "_state_sync",
        "_memory_coordinator",
        "_telemetry_aggregator",
        "_cross_bus_router",
        "_governance_router",
        "_spine",
        "_event_fabric",         # Stage 5 — Unified Event Fabric
    )

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = False
        self._tick_seq = 0
        self._error_count = 0

        # All components lazily assigned in activate()
        self._scheduler: Any = None
        self._state_sync: Any = None
        self._memory_coordinator: Any = None
        self._telemetry_aggregator: Any = None
        self._cross_bus_router: Any = None
        self._governance_router: Any = None
        self._spine: Any = None
        self._event_fabric: Any = None

    # ------------------------------------------------------------------
    # Activation
    # ------------------------------------------------------------------

    def activate(self) -> None:
        """Activate all cognitive infrastructure components.  Idempotent."""
        with self._lock:
            if self._active:
                return
            self._active = True

        _logger.info("UnifiedCognitiveKernel: ACTIVATING")

        # Step 0 — Unified Event Fabric (circulatory system) — must be first
        self._event_fabric = self._boot("UnifiedEventFabric",
                                         "runtime.unified_fabric.unified",
                                         "get_unified_event_fabric")

        # Step 1 — wire event bridges before any ticks
        self._cross_bus_router = self._boot("CrossBusRouter",
                                             "runtime.cross_bus_router",
                                             "get_cross_bus_router")

        # Step 2 — governance routing
        self._governance_router = self._boot("GovernanceRouter",
                                              "runtime.governance_router",
                                              "get_governance_router")

        # Step 3 — urgency-aware scheduler
        self._scheduler = self._boot("CognitionScheduler",
                                      "runtime.cognition_scheduler",
                                      "get_cognition_scheduler")

        # Step 4 — memory auto-capture
        self._memory_coordinator = self._boot("MemoryCoordinator",
                                               "runtime.memory_coordinator",
                                               "get_memory_coordinator")

        # Step 5 — unified telemetry
        self._telemetry_aggregator = self._boot("TelemetryAggregator",
                                                 "runtime.telemetry_aggregator",
                                                 "get_telemetry_aggregator")

        # Step 6 — state sync (no activation needed — stateless reader)
        try:
            from state.state_sync import get_state_sync
            self._state_sync = get_state_sync()
        except Exception as exc:
            _logger.debug("UnifiedCognitiveKernel: StateSync unavailable: %s", exc)

        # Step 7 — cognitive spine last (now all support systems are live)
        self._spine = self._boot("CognitiveSpine",
                                  "runtime.cognitive_spine",
                                  "get_cognitive_spine")

        _logger.info(
            "UnifiedCognitiveKernel: ACTIVE — %d/%d components live",
            self._count_active(),
            8,
        )

    # ------------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------------

    def tick(self, *, ts_ns: int) -> KernelTickResult:
        """Drive one unified cognitive kernel tick.

        1. CognitionScheduler produces the urgency-aware plan.
        2. CognitiveSpine executes all cognitive phases (using the plan).
        3. TelemetryAggregator samples gauges.
        """
        with self._lock:
            self._tick_seq += 1
            seq = self._tick_seq

        urgent_phases: list[str] = []
        phases_ran: dict[str, bool] = {}
        errors = 0

        # Phase A — compute schedule plan
        plan = None
        if self._scheduler is not None:
            try:
                plan = self._scheduler.plan(ts_ns)
                urgent_phases = plan.urgency_signals[-5:]  # last 5 signals
            except Exception as exc:
                errors += 1
                _logger.debug("UnifiedCognitiveKernel: scheduler error: %s", exc)

        # Phase B — drive cognitive spine
        if self._spine is not None:
            try:
                phases_ran = self._spine.tick(ts_ns=ts_ns)
            except Exception as exc:
                errors += 1
                _logger.debug("UnifiedCognitiveKernel: spine error: %s", exc)

        # Phase C — telemetry gauge sampling
        if self._telemetry_aggregator is not None:
            try:
                self._telemetry_aggregator.poll(ts_ns)
            except Exception as exc:
                errors += 1
                _logger.debug("UnifiedCognitiveKernel: telemetry error: %s", exc)

        if errors:
            with self._lock:
                self._error_count += errors

        return KernelTickResult(
            tick_seq=seq,
            ts_ns=ts_ns,
            phases_ran=phases_ran,
            urgent_phases=urgent_phases,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Full unified kernel snapshot for operator dashboard."""
        with self._lock:
            active = self._active
            seq = self._tick_seq
            errs = self._error_count

        out: dict[str, Any] = {
            "kernel": "UnifiedCognitiveKernel",
            "active": active,
            "tick_seq": seq,
            "error_count": errs,
            "components": {
                "scheduler":          self._scheduler is not None,
                "state_sync":         self._state_sync is not None,
                "memory_coordinator": self._memory_coordinator is not None,
                "telemetry":          self._telemetry_aggregator is not None,
                "cross_bus_router":   self._cross_bus_router is not None,
                "governance_router":  self._governance_router is not None,
                "spine":              self._spine is not None,
            },
        }

        # Component sub-snapshots
        for attr, key in (
            ("_event_fabric",        "event_fabric"),
            ("_scheduler",           "scheduler"),
            ("_memory_coordinator",  "memory_coordinator"),
            ("_telemetry_aggregator","telemetry"),
            ("_cross_bus_router",    "cross_bus_router"),
            ("_governance_router",   "governance_router"),
        ):
            obj = getattr(self, attr, None)
            if obj is not None and hasattr(obj, "snapshot"):
                try:
                    out[key] = obj.snapshot()
                except Exception:
                    pass

        return out

    def state_snapshot(self, *, ts_ns: int) -> dict[str, Any]:
        """Full system state snapshot — all subsystems in one call."""
        if self._state_sync is not None:
            try:
                return self._state_sync.snapshot(ts_ns=ts_ns)
            except Exception:
                pass
        return {"error": "state_sync unavailable"}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _boot(self, name: str, module: str, factory: str) -> Any:
        """Import factory, call activate() if present, return singleton."""
        try:
            import importlib
            mod = importlib.import_module(module)
            fn = getattr(mod, factory)
            obj = fn()
            if hasattr(obj, "activate"):
                obj.activate()
            _logger.info("UnifiedCognitiveKernel: %s online", name)
            return obj
        except Exception as exc:
            _logger.debug("UnifiedCognitiveKernel: %s unavailable: %s", name, exc)
            return None

    def _count_active(self) -> int:
        return sum(1 for attr in (
            "_event_fabric", "_cross_bus_router", "_governance_router", "_scheduler",
            "_memory_coordinator", "_telemetry_aggregator", "_state_sync", "_spine",
        ) if getattr(self, attr, None) is not None)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_kernel: UnifiedCognitiveKernel | None = None
_kernel_lock = threading.Lock()


def get_unified_kernel() -> UnifiedCognitiveKernel:
    """Return the process-wide UnifiedCognitiveKernel singleton."""
    global _kernel
    with _kernel_lock:
        if _kernel is None:
            _kernel = UnifiedCognitiveKernel()
    return _kernel


__all__ = [
    "KernelTickResult",
    "UnifiedCognitiveKernel",
    "get_unified_kernel",
]

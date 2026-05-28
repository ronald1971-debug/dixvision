"""UI State Projection — bind dashboard widgets to kernel state only.

Every UI widget that displays system state MUST read from a
:class:`StateProjection` instance, which is a thin read-only view
over the ``SystemKernel`` snapshot. This eliminates mock state
leakage — widgets that cannot get data from the kernel show
"unavailable" instead of fake data.

Usage in route handlers::

    projection = get_state_projection()
    data = projection.mode          # canonical system mode
    data = projection.belief        # canonical BeliefState
    data = projection.services      # service health map
    data = projection.available("intelligence")  # is service up?

If the kernel is not yet booted, all projections return safe defaults
and ``available()`` returns False for all services.

Authority constraints:
- Read-only: no method on this class can mutate kernel state.
- No engine-package imports (only ``core.kernel`` and ``core.contracts``).
- Thread-safe: reads the immutable ``KernelSnapshot``.
"""

from __future__ import annotations

import logging
from typing import Any

from core.coherence.belief_state import BeliefState, Regime
from core.contracts.governance import SystemMode
from core.kernel import KernelPhase, KernelSnapshot, ServiceHealth, SystemKernel

_logger = logging.getLogger(__name__)

# Sentinel for "no kernel available yet"
_EMPTY_SNAPSHOT = KernelSnapshot()


class StateProjection:
    """Read-only projection of kernel state for UI widgets.

    Replaces all dashboard-local mock state. If a widget needs data
    that isn't available in the projection, the correct response is
    to show "unavailable" — NOT to generate mock data.
    """

    __slots__ = ("_kernel",)

    def __init__(self, kernel: SystemKernel | None = None) -> None:
        self._kernel = kernel

    @property
    def _snap(self) -> KernelSnapshot:
        if self._kernel is None:
            return _EMPTY_SNAPSHOT
        return self._kernel.snapshot

    # -- Core projections -----------------------------------------------

    @property
    def mode(self) -> SystemMode:
        """Canonical system mode (PAPER/CANARY/LIVE/etc)."""
        return self._snap.mode

    @property
    def phase(self) -> KernelPhase:
        """Kernel lifecycle phase."""
        return self._snap.phase

    @property
    def belief(self) -> BeliefState:
        """Canonical BeliefState (regime + market view)."""
        return self._snap.belief

    @property
    def regime(self) -> Regime:
        """Current market regime classification."""
        return self._snap.belief.regime

    @property
    def freeze_active(self) -> bool:
        """Whether the global freeze is active."""
        return self._snap.freeze_active

    @property
    def live_execution_blocked(self) -> bool:
        """Whether live execution is blocked."""
        return self._snap.live_execution_blocked

    @property
    def version(self) -> int:
        """Snapshot version (monotonically increasing)."""
        return self._snap.version

    # -- Service health -------------------------------------------------

    @property
    def services(self) -> dict[str, ServiceHealth]:
        """Map of service name → health status."""
        return {s.name: s for s in self._snap.services}

    def available(self, service_name: str) -> bool:
        """Check if a service is available (registered + healthy)."""
        svcs = self.services
        svc = svcs.get(service_name)
        return svc is not None and svc.healthy

    @property
    def is_booted(self) -> bool:
        """Whether the kernel has completed boot."""
        return self._kernel is not None and self._snap.phase != KernelPhase.COLD

    # -- Mode projection for ModeControlBar -----------------------------

    def mode_name(self) -> str:
        """Current mode as a string name."""
        return self._snap.mode.name

    def is_locked(self) -> bool:
        """Whether the system is in LOCKED mode."""
        from core.contracts.mode_effects import effect_for

        eff = effect_for(self._snap.mode)
        return not eff.signals_emit and not eff.executions_dispatch and eff.oversight_kind == "none"

    # -- Engine health projection for EngineStatusGrid ------------------

    def engine_health(self) -> dict[str, dict[str, Any]]:
        """Service health as a widget-ready dict.

        Returns ``{service_name: {"healthy": bool, "detail": str}}``
        for every registered kernel service. Widgets that read engine
        health should use this instead of calling ``check_self()`` on
        each engine directly.
        """
        return {
            s.name: {"healthy": s.healthy, "detail": s.detail}
            for s in self._snap.services
        }

    def engine_health_rows(self) -> list[dict[str, Any]]:
        """Service health as a list of rows for the EngineStatusGrid.

        Each row contains ``engine_name``, ``bucket`` (alive/degraded/
        halted/offline), and ``detail``. Mirrors the vocabulary from
        Build Compiler Spec §6.
        """
        rows: list[dict[str, Any]] = []
        for s in self._snap.services:
            if s.healthy:
                bucket = "alive"
            elif s.detail and "degrad" in s.detail.lower():
                bucket = "degraded"
            elif s.detail and "halt" in s.detail.lower():
                bucket = "halted"
            elif not s.healthy:
                bucket = "offline"
            else:
                bucket = "alive"
            rows.append({
                "engine_name": s.name,
                "bucket": bucket,
                "detail": s.detail,
            })
        return rows

    # -- Cognitive governance projection --------------------------------

    def cognitive_integrity(self) -> dict[str, Any]:
        """Read-only cognitive integrity projection for dashboard widgets.

        Reads the kernel-registered ``cognitive_governance`` service health
        (no direct engine import — authority constraint preserved). Returns
        a dict safe for JSON serialisation.

        When cognitive governance is not yet registered or is unavailable,
        returns a safe-default ``"unavailable"`` payload so the widget can
        show an amber chip rather than crashing.
        """
        svc = self.services.get("cognitive_governance")
        if svc is None:
            return {"available": False, "healthy": False, "detail": "not_registered"}
        return {
            "available": True,
            "healthy": svc.healthy,
            "detail": svc.detail or "",
        }

    # -- JSON-safe summary for API endpoints ----------------------------

    def summary(self) -> dict[str, Any]:
        """JSON-serializable summary for dashboard API endpoints.

        Every field here comes from the kernel — no mock data.
        """
        snap = self._snap
        return {
            "version": snap.version,
            "ts_ns": snap.ts_ns,
            "phase": snap.phase.value,
            "mode": snap.mode.value,
            "regime": snap.belief.regime.value,
            "freeze_active": snap.freeze_active,
            "live_execution_blocked": snap.live_execution_blocked,
            "services": {s.name: {"healthy": s.healthy, "detail": s.detail} for s in snap.services},
        }

    def health_summary(self) -> dict[str, Any]:
        """JSON-serializable health summary for ``/api/health``.

        Provides a kernel-authoritative view of engine health, to be
        used instead of (or alongside) direct ``check_self()`` calls.
        """
        snap = self._snap
        result: dict[str, Any] = {}
        for s in snap.services:
            result[s.name] = {
                "name": s.name,
                "healthy": s.healthy,
                "detail": s.detail,
                "source": "kernel",
            }
        result["_kernel"] = {
            "phase": snap.phase.value,
            "mode": snap.mode.value,
            "version": snap.version,
            "freeze_active": snap.freeze_active,
            "live_execution_blocked": snap.live_execution_blocked,
        }
        return result


# ---------------------------------------------------------------------------
# Module-level accessor
# ---------------------------------------------------------------------------

_PROJECTION: StateProjection | None = None


def init_state_projection(kernel: SystemKernel) -> StateProjection:
    """Initialize the global state projection. Called once at boot."""
    global _PROJECTION
    _PROJECTION = StateProjection(kernel)
    return _PROJECTION


def get_state_projection() -> StateProjection:
    """Get the global state projection for UI widgets.

    Returns a projection backed by the kernel if initialized,
    or an empty projection (all safe defaults) if not yet booted.
    """
    if _PROJECTION is not None:
        return _PROJECTION
    return StateProjection(None)

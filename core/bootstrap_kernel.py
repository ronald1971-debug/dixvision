"""core/bootstrap_kernel.py
DIX VISION v42.2 — System bootstrap entry point.

The :class:`BootstrapKernel` is the single top-level coordinator that
orchestrates the complete system startup lifecycle. It delegates to:

* :mod:`core.bootstrap.startup_sequence` — the ordered boot step runner.
* :mod:`core.bootstrap.dependency_graph` — topological subsystem ordering.
* :mod:`core.bootstrap.lifecycle` — per-engine start/stop/health protocol.

The kernel is the only place that knows *how* to start the whole system
and *whether* it succeeded. Consumers (e.g. the CLI entry point or the
integration test harness) call :meth:`BootstrapKernel.boot` and inspect
the return value; they never reach into the startup internals directly.

Singleton access is provided via :func:`get_bootstrap_kernel` with
double-checked locking.

Authority constraints:
* No imports from any ``*_engine`` package at module level. Optional
  engine hooks are resolved lazily inside :meth:`boot` / :meth:`shutdown`
  so the module remains importable before any engine is available.
* No imports from ``state.ledger`` writers.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from core.bootstrap.dependency_graph import DependencyGraph
from core.bootstrap.lifecycle import LifecycleManager, LifecyclePhase
from core.bootstrap.startup_sequence import StartupResult, run_startup_sequence

logger = logging.getLogger(__name__)


class BootstrapKernel:
    """Top-level boot coordinator for DIX VISION v42.2.

    The kernel manages the complete lifecycle from initial startup
    through to clean shutdown. It holds references to:

    * A :class:`~core.bootstrap.lifecycle.LifecycleManager` that
      tracks per-engine health.
    * A :class:`~core.bootstrap.dependency_graph.DependencyGraph` that
      records the declared order in which subsystems must start.
    * The last :class:`~core.bootstrap.startup_sequence.StartupResult`
      so callers can inspect per-step timing.

    Usage::

        kernel = BootstrapKernel(config_path="registry/config.yaml")
        ok = kernel.boot()
        if not ok:
            sys.exit(1)
        # ... run until shutdown signal ...
        kernel.shutdown()
    """

    def __init__(self, config_path: str | Path | None = None) -> None:
        self._config_path = Path(config_path) if config_path else None
        self._lifecycle = LifecycleManager()
        self._dep_graph = DependencyGraph()
        self._startup_result: StartupResult | None = None
        self._booted = False
        self._shutdown_called = False
        self._lock = threading.Lock()
        self._registered_engines: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Boot
    # ------------------------------------------------------------------

    def boot(
        self,
        *,
        skip_feeds: bool = False,
        skip_plugins: bool = False,
    ) -> bool:
        """Execute the full startup sequence.

        Idempotent — calling :meth:`boot` a second time before
        :meth:`shutdown` is a no-op that returns the result of the
        original boot.

        Args:
            skip_feeds: Passed through to
                :func:`~core.bootstrap.startup_sequence.run_startup_sequence`.
                Set ``True`` in tests that do not need live data feeds.
            skip_plugins: Passed through to
                :func:`~core.bootstrap.startup_sequence.run_startup_sequence`.
                Set ``True`` in tests that do not need plugin registration.

        Returns:
            ``True`` if every boot step succeeded and all registered
            engines are healthy. ``False`` if any step failed or any
            engine reported a health score of 0.0.
        """
        with self._lock:
            if self._booted:
                logger.debug("BootstrapKernel.boot: already booted, returning previous result")
                return self._startup_result is not None and self._startup_result.success

            logger.info("BootstrapKernel: starting boot sequence (config=%s)", self._config_path)

            # 1. Run the canonical startup sequence
            result = run_startup_sequence(
                skip_feeds=skip_feeds,
                skip_plugins=skip_plugins,
            )
            self._startup_result = result

            if not result.success:
                failed = [s.step for s in result.failed_steps]
                logger.error(
                    "BootstrapKernel: boot FAILED — steps: %s; mode=%s",
                    failed,
                    result.final_mode,
                )
                self._booted = True
                return False

            # 2. Build the dependency graph for optional subsystems
            self._build_dependency_graph()

            # 3. Start all registered lifecycle engines in topo order
            all_engines_ok = True
            if self._registered_engines:
                ordered = self._dep_graph.topo_order()
                for engine_name in ordered:
                    engine = self._registered_engines.get(engine_name)
                    if engine is None:
                        continue
                    self._lifecycle.register(engine_name, engine)
                all_engines_ok = self._lifecycle.start_all()

            self._booted = True
            success = result.success and all_engines_ok
            logger.info(
                "BootstrapKernel: boot %s (mode=%s, engines=%d)",
                "OK" if success else "DEGRADED",
                result.final_mode,
                len(self._registered_engines),
            )
            return success

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Return a plain-dict snapshot of the kernel's current state.

        Keys:
        * ``booted``: Whether :meth:`boot` has been called.
        * ``startup_success``: Whether the startup sequence succeeded,
          or ``None`` if not yet booted.
        * ``final_mode``: The mode string from the startup result, or
          ``None`` if not yet booted.
        * ``lifecycle_phase``: Current :class:`LifecyclePhase` string.
        * ``engine_health``: ``{engine_name: health_score}`` dict.
        * ``failed_steps``: List of step names that failed during boot.
        * ``config_path``: The config path (string or ``None``).
        * ``shutdown_called``: Whether :meth:`shutdown` has been called.
        """
        engine_health: dict[str, float] = {}
        if self._booted and self._registered_engines:
            engine_health = self._lifecycle.health_check()

        failed_steps: list[str] = []
        if self._startup_result is not None:
            failed_steps = [s.step for s in self._startup_result.failed_steps]

        return {
            "booted": self._booted,
            "startup_success": (
                self._startup_result.success if self._startup_result else None
            ),
            "final_mode": (
                self._startup_result.final_mode if self._startup_result else None
            ),
            "lifecycle_phase": self._lifecycle.phase.value,
            "engine_health": engine_health,
            "failed_steps": failed_steps,
            "config_path": str(self._config_path) if self._config_path else None,
            "shutdown_called": self._shutdown_called,
        }

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Gracefully stop all managed engines in reverse start order.

        Idempotent — calling :meth:`shutdown` multiple times is safe.
        """
        with self._lock:
            if self._shutdown_called:
                logger.debug("BootstrapKernel.shutdown: already called")
                return
            self._shutdown_called = True

        logger.info("BootstrapKernel: initiating shutdown")
        try:
            self._lifecycle.stop_all()
        except Exception as exc:
            logger.error("BootstrapKernel: error during lifecycle stop_all: %s", exc)

        logger.info("BootstrapKernel: shutdown complete")

    # ------------------------------------------------------------------
    # Engine registration (optional — for subsystems that expose the
    # Engine protocol defined in core.bootstrap.lifecycle)
    # ------------------------------------------------------------------

    def register_engine(self, name: str, engine: Any, *depends_on: str) -> None:
        """Register a lifecycle-managed engine with optional dependencies.

        Must be called *before* :meth:`boot`. After :meth:`boot` has
        been called, registration is ignored and a warning is emitted.

        Args:
            name: Unique subsystem name.
            engine: Object implementing ``start() / stop() / health()``
                (the :class:`~core.bootstrap.lifecycle.Engine` protocol).
            depends_on: Names of engines that must start before this one.
        """
        if self._booted:
            logger.warning(
                "BootstrapKernel.register_engine: kernel already booted, "
                "ignoring registration of %r",
                name,
            )
            return
        self._registered_engines[name] = engine
        self._dep_graph.add(name, *depends_on)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_dependency_graph(self) -> None:
        """Populate the dependency graph with default subsystem ordering.

        The default ordering mirrors the startup sequence defined in
        :mod:`core.bootstrap.startup_sequence`:
        governance → intelligence → execution → learning → system.
        """
        self._dep_graph.add("governance")
        self._dep_graph.add("intelligence", "governance")
        self._dep_graph.add("execution", "intelligence")
        self._dep_graph.add("learning", "governance")
        self._dep_graph.add("system", "execution", "learning")

    def __repr__(self) -> str:
        phase = self._lifecycle.phase.value
        return (
            f"BootstrapKernel("
            f"booted={self._booted}, "
            f"phase={phase!r}, "
            f"config={self._config_path!r})"
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_kernel_instance: BootstrapKernel | None = None
_kernel_lock = threading.Lock()


def get_bootstrap_kernel(
    *,
    config_path: str | Path | None = None,
) -> BootstrapKernel:
    """Return the process-level :class:`BootstrapKernel` singleton.

    Double-checked locking — safe for concurrent first-calls during
    startup.

    Args:
        config_path: Path to the system configuration file. Only used
            on the *first* call that creates the singleton. Subsequent
            calls ignore this parameter.

    Returns:
        The singleton :class:`BootstrapKernel` instance.
    """
    global _kernel_instance
    if _kernel_instance is None:
        with _kernel_lock:
            if _kernel_instance is None:
                _kernel_instance = BootstrapKernel(config_path=config_path)
    return _kernel_instance


def _reset_bootstrap_kernel_for_tests() -> None:
    """Reset the singleton — for use in tests only.

    Never call this in production code.
    """
    global _kernel_instance
    with _kernel_lock:
        _kernel_instance = None


__all__ = [
    "BootstrapKernel",
    "get_bootstrap_kernel",
]

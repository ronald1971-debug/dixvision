"""runtime.cognition_daemon — Independent Cognitive Runtime Loop.

INDIRA and DYON must remain alive even when the execution fabric is
degraded, halted, or not yet booted.  The kernel's tick loop is
execution-fabric-centric; cognition is coupled to that lifecycle, which
violates the Master Directive (COGNITIVE INTEGRITY > SYSTEM INTEGRITY >
CAPITAL INTEGRITY).

CognitionDaemon runs as its OWN asyncio task and delegates all cognitive
sequencing to CognitiveSpine — the single authoritative cognitive driver:

  - Activates the spine (CognitiveTelemetry, DyonSignalBridge, TraderIntelligence)
  - Drives spine.tick() on a unified cadence (default 2s)
  - Publishes daemon heartbeats to the event bus every 30s
  - Continues running if execution fabric is degraded or absent
  - Never imports execution_engine; authority boundary preserved (B1)

INV-15: all ts_ns values are sourced from the caller-supplied time_source.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from system import time_source

_logger = logging.getLogger(__name__)


class DaemonState(StrEnum):
    COLD = "COLD"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"


@dataclass
class CognitionDaemonConfig:
    spine_interval_ms: float = 2000.0    # unified cognitive tick cadence
    heartbeat_interval_s: float = 30.0   # event-bus heartbeat cadence
    startup_delay_ms: float = 500.0      # give the rest of boot time to settle


class CognitionDaemon:
    """Autonomous cognitive loop — independent of execution fabric state.

    Both intelligences (INDIRA, DYON) are alive and observing as long as
    the process is alive.  The operator always has visibility.

    All cognitive sequencing is delegated to CognitiveSpine.
    """

    __slots__ = (
        "_config",
        "_state",
        "_spine_task",
        "_heartbeat_task",
        "_kernel",
        "_tick_seq",
    )

    def __init__(self, config: CognitionDaemonConfig | None = None) -> None:
        self._config = config or CognitionDaemonConfig()
        self._state = DaemonState.COLD
        self._spine_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._kernel: Any = None  # UnifiedCognitiveKernel (replaces _spine)
        self._tick_seq: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Launch daemon coroutines as asyncio tasks.

        Safe to call from inside an already-running event loop (server
        startup).  Idempotent — second call is a no-op.
        """
        if self._state == DaemonState.RUNNING:
            return
        self._state = DaemonState.RUNNING
        self._spine_task = asyncio.create_task(
            self._spine_loop(), name="cognition_daemon.spine"
        )
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(), name="cognition_daemon.heartbeat"
        )
        _logger.info(
            "CognitionDaemon started (spine=%.0fms)",
            self._config.spine_interval_ms,
        )

    async def stop(self) -> None:
        """Gracefully cancel all daemon tasks."""
        self._state = DaemonState.STOPPED
        for task in (self._spine_task, self._heartbeat_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        _logger.info("CognitionDaemon stopped after %d cycles", self._tick_seq)

    # ------------------------------------------------------------------
    # Spine loop — unified cognitive tick
    # ------------------------------------------------------------------

    async def _spine_loop(self) -> None:
        """Drive UnifiedCognitiveKernel continuously on the unified cadence."""
        await asyncio.sleep(self._config.startup_delay_ms / 1000.0)
        interval_s = self._config.spine_interval_ms / 1000.0

        # Activate the full kernel (idempotent) in a thread so the event loop
        # stays responsive during the one-time boot of all cognitive subsystems
        # (memory coordinator, INDIRA, DYON, telemetry, etc.).
        kernel = self._get_kernel()
        if kernel is not None:
            try:
                await asyncio.to_thread(kernel.activate)
            except Exception as exc:
                _logger.debug("CognitionDaemon: kernel.activate error: %s", exc)

        _logger.info("CognitionDaemon: kernel loop active (%.0fms)", self._config.spine_interval_ms)

        while self._state == DaemonState.RUNNING:
            ts_ns = time_source.wall_ns()
            try:
                k = self._get_kernel()
                if k is not None:
                    # Run the synchronous cognitive tick in a thread pool so the
                    # asyncio event loop remains responsive during INDIRA/DYON work.
                    await asyncio.to_thread(k.tick, ts_ns=ts_ns)
                    self._tick_seq += 1
            except Exception as exc:
                _logger.debug("CognitionDaemon: kernel tick error: %s", exc)
            try:
                await asyncio.sleep(interval_s)
            except asyncio.CancelledError:
                return

    # ------------------------------------------------------------------
    # Heartbeat loop
    # ------------------------------------------------------------------

    async def _heartbeat_loop(self) -> None:
        """Publish daemon liveness to the event bus every heartbeat_interval_s."""
        while self._state == DaemonState.RUNNING:
            try:
                await asyncio.sleep(self._config.heartbeat_interval_s)
            except asyncio.CancelledError:
                return
            ts_ns = time_source.wall_ns()
            kernel_active = self._kernel is not None
            try:
                from state.event_bus import CognitiveChannel, get_event_bus
                get_event_bus().publish(CognitiveChannel.INDIRA_THOUGHT, {
                    "source": "cognition_daemon",
                    "event": "HEARTBEAT",
                    "kernel_active": kernel_active,
                    "tick_seq": self._tick_seq,
                    "ts_ns": ts_ns,
                })
            except Exception:
                pass
            _logger.debug(
                "CognitionDaemon heartbeat: tick_seq=%d kernel=%s",
                self._tick_seq,
                kernel_active,
            )

    # ------------------------------------------------------------------
    # Lazy singletons (best-effort — never block boot)
    # ------------------------------------------------------------------

    def _get_kernel(self) -> Any:
        if self._kernel is not None:
            return self._kernel
        try:
            from runtime.unified_kernel import get_unified_kernel
            self._kernel = get_unified_kernel()
        except Exception:
            pass
        return self._kernel

    # ------------------------------------------------------------------
    # Read surface
    # ------------------------------------------------------------------

    @property
    def state(self) -> DaemonState:
        return self._state

    @property
    def tick_seq(self) -> int:
        return self._tick_seq

    def snapshot(self) -> dict[str, Any]:
        kernel_snap: dict[str, Any] = {}
        try:
            k = self._get_kernel()
            if k is not None:
                kernel_snap = k.snapshot()
        except Exception:
            pass
        return {
            "daemon": "CognitionDaemon",
            "state": self._state.value,
            "tick_seq": self._tick_seq,
            "kernel_active": self._kernel is not None,
            "config": {
                "spine_interval_ms": self._config.spine_interval_ms,
            },
            "kernel": kernel_snap,
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_daemon: CognitionDaemon | None = None


def get_cognition_daemon(config: CognitionDaemonConfig | None = None) -> CognitionDaemon:
    """Return the process-wide CognitionDaemon singleton."""
    global _daemon
    if _daemon is None:
        _daemon = CognitionDaemon(config)
    return _daemon


__all__ = [
    "CognitionDaemon",
    "CognitionDaemonConfig",
    "DaemonState",
    "get_cognition_daemon",
]

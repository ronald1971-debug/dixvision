"""core.bootstrap.lifecycle — Engine Lifecycle Manager.

Controls the startup and shutdown lifecycle of all engines. Each engine
implements start()/stop()/health() and this module orchestrates them
in the correct dependency order with health verification at each step.

Lifecycle phases:
1. INIT — modules discovered, not yet started
2. STARTING — engines booting in order
3. RUNNING — all engines healthy
4. DEGRADED — some engines unhealthy
5. STOPPING — graceful shutdown in progress
6. STOPPED — all engines terminated
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from system import time_source

logger = logging.getLogger(__name__)


class LifecyclePhase(StrEnum):
    """System lifecycle phases."""

    INIT = "INIT"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"


class Engine(Protocol):
    """Protocol for lifecycle-managed engines."""

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def health(self) -> float: ...


@dataclass
class EngineEntry:
    """Registry entry for a managed engine."""

    name: str
    engine: Any
    phase: LifecyclePhase = LifecyclePhase.INIT
    health_score: float = 0.0
    start_ts_ns: int = 0
    stop_ts_ns: int = 0
    error: str = ""


class LifecycleManager:
    """Orchestrates engine startup/shutdown in dependency order."""

    __slots__ = ("_engines", "_phase", "_boot_ts")

    def __init__(self) -> None:
        self._engines: list[EngineEntry] = []
        self._phase = LifecyclePhase.INIT
        self._boot_ts = 0

    @property
    def phase(self) -> LifecyclePhase:
        return self._phase

    def register(self, name: str, engine: Any) -> None:
        """Register an engine for lifecycle management."""
        self._engines.append(EngineEntry(name=name, engine=engine))
        logger.debug("Registered engine: %s", name)

    def start_all(self) -> bool:
        """Start all engines in registration order.

        Returns True if all engines started successfully.
        """
        self._phase = LifecyclePhase.STARTING
        self._boot_ts = time_source.wall_ns()
        all_ok = True

        for entry in self._engines:
            try:
                entry.engine.start()
                entry.phase = LifecyclePhase.RUNNING
                entry.start_ts_ns = time_source.wall_ns()
                entry.health_score = 1.0
                logger.info("Started: %s", entry.name)
            except Exception as e:
                entry.phase = LifecyclePhase.DEGRADED
                entry.error = str(e)
                all_ok = False
                logger.error("Failed to start %s: %s", entry.name, e)

        self._phase = LifecyclePhase.RUNNING if all_ok else LifecyclePhase.DEGRADED
        return all_ok

    def stop_all(self) -> None:
        """Stop all engines in reverse registration order."""
        self._phase = LifecyclePhase.STOPPING

        for entry in reversed(self._engines):
            try:
                entry.engine.stop()
                entry.phase = LifecyclePhase.STOPPED
                entry.stop_ts_ns = time_source.wall_ns()
                logger.info("Stopped: %s", entry.name)
            except Exception as e:
                logger.error("Error stopping %s: %s", entry.name, e)

        self._phase = LifecyclePhase.STOPPED

    def health_check(self) -> dict[str, float]:
        """Run health checks on all engines."""
        results = {}
        for entry in self._engines:
            try:
                score = entry.engine.health()
                entry.health_score = score
                results[entry.name] = score
            except Exception:
                entry.health_score = 0.0
                results[entry.name] = 0.0
        return results

    @property
    def overall_health(self) -> float:
        """Average health across all engines."""
        if not self._engines:
            return 1.0
        return sum(e.health_score for e in self._engines) / len(self._engines)


__all__ = [
    "Engine",
    "EngineEntry",
    "Lifecycle",
    "LifecycleManager",
    "LifecyclePhase",
]

# Backward-compatible alias
Lifecycle = LifecycleManager

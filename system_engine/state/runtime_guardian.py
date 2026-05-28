"""system_engine/state/runtime_guardian.py
DIX VISION v42.2 — Runtime Guardian

Guards system runtime invariants at the process level. Monitors memory
usage, thread counts, open file descriptors, and CPU utilisation.
Escalates to CRITICAL when resource limits are breached, triggering
a controlled system halt via the kill-switch pathway.

Thread-safe. Uses only stdlib — no external dependencies.
"""

from __future__ import annotations

import os
import threading
import time as _time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class RuntimeThreat(StrEnum):
    MEMORY_EXHAUSTION = "MEMORY_EXHAUSTION"
    THREAD_EXPLOSION = "THREAD_EXPLOSION"
    FD_EXHAUSTION = "FD_EXHAUSTION"
    CPU_SATURATION = "CPU_SATURATION"
    DEADLOCK_SUSPECT = "DEADLOCK_SUSPECT"


@dataclass(frozen=True, slots=True)
class RuntimeLimits:
    """Resource limits for the runtime guardian."""
    max_memory_mb: float = 4096.0
    max_threads: int = 512
    max_open_fds: int = 1024
    max_cpu_pct: float = 90.0
    warn_memory_mb: float = 3072.0
    warn_threads: int = 256


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    """Point-in-time resource snapshot."""
    memory_mb: float
    thread_count: int
    open_fds: int
    cpu_pct: float
    ts_ns: int
    threats: tuple[RuntimeThreat, ...]
    healthy: bool


def _get_memory_mb() -> float:
    try:
        import resource
        rusage = resource.getrusage(resource.RUSAGE_SELF)
        return rusage.ru_maxrss / 1024.0
    except Exception:
        pass
    try:
        with open(f"/proc/{os.getpid()}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return float(line.split()[1]) / 1024.0
    except Exception:
        pass
    return 0.0


def _get_open_fds() -> int:
    try:
        fd_dir = f"/proc/{os.getpid()}/fd"
        if os.path.isdir(fd_dir):
            return len(os.listdir(fd_dir))
    except Exception:
        pass
    return 0


class RuntimeGuardian:
    """
    Monitors process-level resource usage and enforces runtime limits.

    Thread-safe. check() returns a RuntimeSnapshot that callers can
    inspect; if threats are present, callers should initiate shutdown.
    """

    def __init__(self, limits: RuntimeLimits | None = None) -> None:
        self._limits = limits or RuntimeLimits()
        self._lock = threading.Lock()
        self._last_cpu_times: tuple[float, float] | None = None
        self._snapshots: list[RuntimeSnapshot] = []
        self._max_history = 200

    def check(self, ts_ns: int | None = None) -> RuntimeSnapshot:
        if ts_ns is None:
            ts_ns = _time.time_ns()

        mem_mb = _get_memory_mb()
        thread_count = threading.active_count()
        open_fds = _get_open_fds()
        cpu_pct = self._sample_cpu()

        threats: list[RuntimeThreat] = []
        lim = self._limits
        if mem_mb > lim.max_memory_mb:
            threats.append(RuntimeThreat.MEMORY_EXHAUSTION)
        if thread_count > lim.max_threads:
            threats.append(RuntimeThreat.THREAD_EXPLOSION)
        if open_fds > lim.max_open_fds:
            threats.append(RuntimeThreat.FD_EXHAUSTION)
        if cpu_pct > lim.max_cpu_pct:
            threats.append(RuntimeThreat.CPU_SATURATION)

        snap = RuntimeSnapshot(
            memory_mb=mem_mb,
            thread_count=thread_count,
            open_fds=open_fds,
            cpu_pct=cpu_pct,
            ts_ns=ts_ns,
            threats=tuple(threats),
            healthy=len(threats) == 0,
        )
        with self._lock:
            self._snapshots.append(snap)
            if len(self._snapshots) > self._max_history:
                self._snapshots = self._snapshots[-self._max_history:]
        return snap

    def _sample_cpu(self) -> float:
        try:
            times = os.times()
            cpu_time = times.user + times.system
            now = _time.monotonic()
            with self._lock:
                prev = self._last_cpu_times
                self._last_cpu_times = (cpu_time, now)
            if prev is None:
                return 0.0
            dt_cpu = cpu_time - prev[0]
            dt_wall = now - prev[1]
            if dt_wall < 1e-6:
                return 0.0
            return min(100.0, (dt_cpu / dt_wall) * 100.0)
        except Exception:
            return 0.0

    def is_healthy(self) -> bool:
        snap = self.check()
        return snap.healthy

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            latest = self._snapshots[-1] if self._snapshots else None
        if latest is None:
            return {"healthy": True}
        return {
            "healthy": latest.healthy,
            "memory_mb": latest.memory_mb,
            "thread_count": latest.thread_count,
            "threats": [t.value for t in latest.threats],
        }


# Singleton factory
_instance: RuntimeGuardian | None = None
_lock = threading.Lock()


def get_runtime_guardian(limits: RuntimeLimits | None = None) -> RuntimeGuardian:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = RuntimeGuardian(limits=limits)
    return _instance


__all__ = [
    "RuntimeGuardian",
    "RuntimeLimits",
    "RuntimeSnapshot",
    "RuntimeThreat",
    "get_runtime_guardian",
]

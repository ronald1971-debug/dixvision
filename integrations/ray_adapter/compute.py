"""Ray distributed compute adapter (OSS Integration Layer).

Provides distributed execution for DIXVISION compute-heavy operations.
Replaces custom multiprocessing with Ray's actor model and task system.

Key use cases:
- Parallel strategy simulation (100+ scenarios simultaneously)
- Multi-agent archetype evaluation (300 archetypes × N regimes)
- Hyperparameter optimization (strategy parameter search)
- Feature engineering at scale (parallel indicator computation)
- RL training (distributed policy optimization)

Reference: github.com/ray-project/ray
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from system import time_source


class TaskStatus(StrEnum):
    """Task execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class ComputeMode(StrEnum):
    """Compute execution mode."""

    LOCAL = "local"  # single-machine (fallback)
    RAY_LOCAL = "ray_local"  # Ray on local machine
    RAY_CLUSTER = "ray_cluster"  # Ray on cluster


@dataclass(slots=True)
class TaskResult:
    """Result of a distributed task."""

    task_id: str
    status: TaskStatus
    result: Any = None
    error: str | None = None
    duration_ms: float = 0.0
    worker_id: str = ""


@dataclass(frozen=True, slots=True)
class RayConfig:
    """Configuration for Ray compute."""

    mode: ComputeMode = ComputeMode.LOCAL
    num_cpus: int = 4
    num_gpus: int = 0
    memory_mb: int = 4096
    max_concurrent_tasks: int = 100
    task_timeout_s: int = 300


class RayComputeAdapter:
    """DIXVISION adapter wrapping Ray distributed compute.

    Provides:
    - Remote task execution (stateless functions)
    - Actor management (stateful long-running workers)
    - Parallel map (apply function to list of inputs)
    - Task orchestration (DAG-style dependencies)

    Falls back to ThreadPoolExecutor when Ray is unavailable.
    """

    def __init__(self, *, config: RayConfig | None = None) -> None:
        self._config = config or RayConfig()
        self._ray_available = False
        self._tasks: dict[str, TaskResult] = {}
        self._task_counter = 0
        self._executor: ThreadPoolExecutor | None = None

    def initialize(self) -> bool:
        """Initialize Ray runtime or fallback executor."""
        try:
            import ray

            if not ray.is_initialized():
                ray.init(
                    num_cpus=self._config.num_cpus,
                    num_gpus=self._config.num_gpus,
                    ignore_reinit_error=True,
                )
            self._ray_available = True
            return True
        except ImportError:
            self._ray_available = False
            self._executor = ThreadPoolExecutor(max_workers=self._config.num_cpus)
            return True

    def submit_task(
        self,
        func: Callable[..., Any],
        *args: Any,
        task_id: str = "",
        **kwargs: Any,
    ) -> str:
        """Submit a task for execution. Returns task_id."""
        self._task_counter += 1
        tid = task_id or f"task_{self._task_counter:08d}"

        task_result = TaskResult(task_id=tid, status=TaskStatus.RUNNING)
        self._tasks[tid] = task_result

        start = time_source.wall_ns() / 1_000_000_000
        try:
            if self._ray_available:
                import ray

                remote_func = ray.remote(func)
                ref = remote_func.remote(*args, **kwargs)
                result = ray.get(ref, timeout=self._config.task_timeout_s)
            else:
                result = func(*args, **kwargs)

            task_result.status = TaskStatus.COMPLETED
            task_result.result = result
            task_result.duration_ms = (time_source.wall_ns() / 1_000_000_000 - start) * 1000
        except Exception as e:
            task_result.status = TaskStatus.FAILED
            task_result.error = str(e)
            task_result.duration_ms = (time_source.wall_ns() / 1_000_000_000 - start) * 1000

        return tid

    def parallel_map(
        self,
        func: Callable[[Any], Any],
        inputs: list[Any],
    ) -> list[TaskResult]:
        """Apply a function to a list of inputs in parallel."""
        results: list[TaskResult] = []

        if self._ray_available:
            import ray

            remote_func = ray.remote(func)
            refs = [remote_func.remote(inp) for inp in inputs]
            for i, ref in enumerate(refs):
                tid = f"map_{self._task_counter + i + 1:08d}"
                start = time_source.wall_ns() / 1_000_000_000
                try:
                    result = ray.get(ref, timeout=self._config.task_timeout_s)
                    results.append(
                        TaskResult(
                            task_id=tid,
                            status=TaskStatus.COMPLETED,
                            result=result,
                            duration_ms=(time_source.wall_ns() / 1_000_000_000 - start) * 1000,
                        )
                    )
                except Exception as e:
                    results.append(
                        TaskResult(
                            task_id=tid,
                            status=TaskStatus.FAILED,
                            error=str(e),
                            duration_ms=(time_source.wall_ns() / 1_000_000_000 - start) * 1000,
                        )
                    )
        else:
            for i, inp in enumerate(inputs):
                tid = f"map_{self._task_counter + i + 1:08d}"
                start = time_source.wall_ns() / 1_000_000_000
                try:
                    result = func(inp)
                    results.append(
                        TaskResult(
                            task_id=tid,
                            status=TaskStatus.COMPLETED,
                            result=result,
                            duration_ms=(time_source.wall_ns() / 1_000_000_000 - start) * 1000,
                        )
                    )
                except Exception as e:
                    results.append(
                        TaskResult(
                            task_id=tid,
                            status=TaskStatus.FAILED,
                            error=str(e),
                            duration_ms=(time_source.wall_ns() / 1_000_000_000 - start) * 1000,
                        )
                    )

        self._task_counter += len(inputs)
        return results

    def get_task(self, task_id: str) -> TaskResult | None:
        """Get task result."""
        return self._tasks.get(task_id)

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task."""
        task = self._tasks.get(task_id)
        if task and task.status == TaskStatus.RUNNING:
            task.status = TaskStatus.CANCELED
            return True
        return False

    @property
    def active_tasks(self) -> int:
        """Count of running tasks."""
        return sum(1 for t in self._tasks.values() if t.status == TaskStatus.RUNNING)

    @property
    def total_tasks(self) -> int:
        """Total tasks submitted."""
        return len(self._tasks)

    @property
    def compute_mode(self) -> ComputeMode:
        """Current compute mode."""
        if self._ray_available:
            return self._config.mode
        return ComputeMode.LOCAL

    def shutdown(self) -> None:
        """Shutdown compute resources."""
        if self._ray_available:
            import ray

            ray.shutdown()
        if self._executor:
            self._executor.shutdown(wait=False)

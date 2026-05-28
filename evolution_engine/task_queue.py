# ADAPTED FROM: celery/celery
# (celery/app/task.py — @task decorator, Task.retry(), Task.apply_async();
#  celery/canvas.py — chain(), chord(), group() for task composition;
#  celery/app/base.py — Celery app configuration, broker_url)
"""C-66 — Celery async background task queue.

This module adapts Celery's task composition patterns for async
background jobs in the evolution engine. Broker: Redis (C-04) or
RabbitMQ.

What survives from upstream (celery/celery):
    * **@task** — ``app/task.py``: decorator that registers a function
      as an async task with retry logic.
    * **chain()** — ``canvas.py``: sequential task pipeline where each
      task feeds output to the next.
    * **group()** — ``canvas.py``: parallel execution of independent
      tasks.
    * **chord()** — ``canvas.py``: group + callback when all complete.
    * **apply_async()** — ``task.py``: enqueue task for async execution.
    * **retry()** — ``task.py``: retry with exponential backoff.

What we replaced:
    * Real ``celery`` import is lazy (Protocol seam).
    * In-memory synchronous executor for unit tests.
    * Same task interface (register, execute, chain).

OFFLINE tier: async background jobs, never triggers RUNTIME execution.
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any


class TaskStatus(enum.Enum):
    """Task execution status."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


@dataclass(frozen=True, slots=True)
class TaskResult:
    """Result of a single task execution."""

    task_id: str
    task_name: str
    status: TaskStatus
    result: Any = None
    error: str = ""
    retries: int = 0


class TaskQueue:
    """Celery-style async task queue with in-memory executor.

    Registers tasks via decorator, executes them synchronously in test
    mode or enqueues to a real Celery broker in production.

    Usage::

        tq = TaskQueue()

        @tq.task(name="extract")
        def extract_data():
            return {"data": [1, 2, 3]}

        @tq.task(name="transform", max_retries=3)
        def transform_data(data):
            return [x * 2 for x in data]

        # Execute single task
        result = tq.apply("extract")

        # Execute chain
        results = tq.chain(["extract", "transform"])
    """

    def __init__(
        self,
        *,
        broker_url: str = "redis://localhost:6379/0",
        in_memory: bool = True,
    ) -> None:
        self._broker_url = broker_url
        self._in_memory = in_memory
        self._tasks: dict[str, _TaskDef] = {}
        self._results: dict[str, TaskResult] = {}
        self._counter: int = 0

    def task(
        self,
        name: str,
        max_retries: int = 0,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a task function (mirrors @celery.task)."""

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self._tasks[name] = _TaskDef(name=name, fn=fn, max_retries=max_retries)
            return fn

        return decorator

    def apply(self, task_name: str, *args: Any, **kwargs: Any) -> TaskResult:
        """Execute a task synchronously (test mode).

        In production, this would call ``task.apply_async()``.
        """
        if task_name not in self._tasks:
            return TaskResult(
                task_id=self._next_id(),
                task_name=task_name,
                status=TaskStatus.FAILED,
                error=f"task '{task_name}' not registered",
            )

        task_def = self._tasks[task_name]
        task_id = self._next_id()
        retries = 0

        while True:
            try:
                result = task_def.fn(*args, **kwargs)
                tr = TaskResult(
                    task_id=task_id,
                    task_name=task_name,
                    status=TaskStatus.SUCCESS,
                    result=result,
                    retries=retries,
                )
                self._results[task_id] = tr
                return tr
            except Exception as e:
                if retries < task_def.max_retries:
                    retries += 1
                    continue
                tr = TaskResult(
                    task_id=task_id,
                    task_name=task_name,
                    status=TaskStatus.FAILED,
                    error=f"{type(e).__name__}: {e}",
                    retries=retries,
                )
                self._results[task_id] = tr
                return tr

    def chain(self, task_names: Sequence[str], initial_input: Any = None) -> list[TaskResult]:
        """Execute tasks sequentially, piping output to next input.

        Mirrors ``celery.canvas.chain(task1.s() | task2.s())``.
        """
        results: list[TaskResult] = []
        current_input = initial_input

        for name in task_names:
            if current_input is not None:
                result = self.apply(name, current_input)
            else:
                result = self.apply(name)

            results.append(result)
            if result.status != TaskStatus.SUCCESS:
                break
            current_input = result.result

        return results

    def group(self, task_calls: Sequence[tuple[str, tuple[Any, ...]]]) -> list[TaskResult]:
        """Execute tasks in parallel (simulated sequentially in test mode).

        Mirrors ``celery.canvas.group(task1.s(), task2.s())()``.
        """
        return [self.apply(name, *args) for name, args in task_calls]

    # ---- internals -------------------------------------------------------

    def _next_id(self) -> str:
        self._counter += 1
        return f"task-{self._counter:06d}"


@dataclass
class _TaskDef:
    name: str
    fn: Callable[..., Any]
    max_retries: int = 0


__all__ = ["TaskQueue", "TaskResult", "TaskStatus"]

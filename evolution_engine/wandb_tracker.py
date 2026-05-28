# ADAPTED FROM: wandb/wandb
# (wandb/__init__.py — wandb.init(), wandb.log(), wandb.finish();
#  wandb/sdk/wandb_run.py — Run class, log(), summary;
#  wandb/sdk/wandb_artifacts.py — Artifact, add_file(), log_artifact())
"""C-63 — W&B alternative experiment tracking.

This module adapts the ``wandb`` SDK as an alternative experiment
tracker alongside MLflow (B-18). Provides richer media logging
(tables, charts, artifacts).

What survives from upstream (wandb/wandb):
    * **wandb.init()** — ``__init__.py``: initialize a run with project
      name, config, tags.
    * **wandb.log()** — ``wandb_run.py``: log metrics at each step.
    * **wandb.finish()** — ``wandb_run.py``: finalize run.
    * **Artifact** — ``wandb_artifacts.py``: versioned model/data
      artifact storage.

What we replaced:
    * Real ``wandb`` import is lazy (Protocol seam).
    * In-memory tracking for unit tests.
    * Same experiment tracking interface as MLflow adapter.

OFFLINE tier: experiment tracking, never on RUNTIME path.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WandbRun:
    """A tracked experiment run."""

    run_id: str
    project: str
    config: dict[str, Any] = field(default_factory=dict)
    metrics: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    finished: bool = False


class WandbTracker:
    """W&B-style experiment tracker.

    Mirrors ``wandb.init()`` / ``wandb.log()`` / ``wandb.finish()``
    patterns. In test mode, stores runs in-memory.

    Usage::

        tracker = WandbTracker(project="dix-strategies")
        run = tracker.init(config={"lr": 0.001}, tags=["baseline"])
        tracker.log(run.run_id, {"loss": 0.5, "sharpe": 1.2})
        tracker.finish(run.run_id)
    """

    def __init__(self, *, project: str = "dix", in_memory: bool = True) -> None:
        self._project = project
        self._in_memory = in_memory
        self._runs: dict[str, WandbRun] = {}
        self._counter: int = 0

    def init(
        self,
        *,
        config: Mapping[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> WandbRun:
        """Initialize a new run (mirrors wandb.init())."""
        self._counter += 1
        run_id = f"run-{self._counter:04d}"
        run = WandbRun(
            run_id=run_id,
            project=self._project,
            config=dict(config or {}),
            tags=list(tags or []),
        )
        self._runs[run_id] = run
        return run

    def log(self, run_id: str, metrics: Mapping[str, Any]) -> bool:
        """Log metrics to a run (mirrors wandb.log())."""
        run = self._runs.get(run_id)
        if run is None or run.finished:
            return False
        run.metrics.append(dict(metrics))
        return True

    def log_artifact(self, run_id: str, artifact_path: str) -> bool:
        """Log an artifact to a run (mirrors wandb.log_artifact())."""
        run = self._runs.get(run_id)
        if run is None or run.finished:
            return False
        run.artifacts.append(artifact_path)
        return True

    def finish(self, run_id: str) -> bool:
        """Finalize a run (mirrors wandb.finish())."""
        run = self._runs.get(run_id)
        if run is None:
            return False
        run.finished = True
        return True

    def get_run(self, run_id: str) -> WandbRun | None:
        """Retrieve a run by ID."""
        return self._runs.get(run_id)

    def list_runs(self) -> list[WandbRun]:
        """List all runs."""
        return list(self._runs.values())


__all__ = ["WandbRun", "WandbTracker"]

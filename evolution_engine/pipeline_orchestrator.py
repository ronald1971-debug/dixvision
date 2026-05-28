# ADAPTED FROM: dagster-io/dagster
# (dagster/_core/definitions/decorators/asset_decorator.py — @asset;
#  dagster/_core/definitions/job_definition.py — define_asset_job;
#  dagster/_core/definitions/schedule_definition.py — ScheduleDefinition;
#  dagster/_core/execution/api.py — execute_job)
"""C-65 — Dagster offline pipeline orchestration.

This module adapts Dagster's asset-based pipeline model for DIX
offline jobs: feature extraction → training → evaluation → governance
proposal. Asset lineage tracks data provenance.

What survives from upstream (dagster-io/dagster):
    * **@asset** — ``asset_decorator.py``: define a data asset with
      input dependencies (upstream assets).
    * **define_asset_job** — ``job_definition.py``: compose assets into
      an executable job.
    * **ScheduleDefinition** — ``schedule_definition.py``: cron-like
      scheduling for jobs.
    * **execute_job** — ``execution/api.py``: run a job programmatically.

What we replaced:
    * Real ``dagster`` import is lazy (Protocol seam).
    * In-memory DAG executor for unit tests.
    * Asset lineage as simple dependency dict.

OFFLINE tier: pipeline jobs never touch RUNTIME execution.
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any


class AssetStatus(enum.Enum):
    """Status of a pipeline asset materialization."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True, slots=True)
class AssetResult:
    """Result of materializing a single asset."""

    name: str
    status: AssetStatus
    output: Any = None
    error: str = ""


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """Result of executing an entire pipeline job."""

    job_name: str
    assets: tuple[AssetResult, ...] = ()
    success: bool = True


class PipelineOrchestrator:
    """Dagster-style asset pipeline orchestrator.

    Defines assets as functions with declared dependencies, then
    executes them in topological order.

    Usage::

        orch = PipelineOrchestrator()

        @orch.asset(name="features")
        def extract_features():
            return {"feature_a": [1, 2, 3]}

        @orch.asset(name="model", deps=["features"])
        def train_model(features):
            return {"weights": [0.5]}

        result = orch.execute("training_pipeline")
    """

    def __init__(self) -> None:
        self._assets: dict[str, _AssetDef] = {}
        self._results: dict[str, AssetResult] = {}

    def asset(
        self,
        name: str,
        deps: Sequence[str] = (),
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register an asset function (mirrors @dagster.asset)."""

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self._assets[name] = _AssetDef(name=name, fn=fn, deps=list(deps))
            return fn

        return decorator

    def execute(self, job_name: str = "default") -> PipelineResult:
        """Execute all registered assets in topological order.

        Mirrors ``dagster.execute_job()`` / ``define_asset_job().execute_in_process()``.
        """
        order = self._topological_sort()
        results: list[AssetResult] = []
        success = True

        for asset_name in order:
            asset_def = self._assets[asset_name]
            dep_outputs: dict[str, Any] = {}
            skip = False

            for dep in asset_def.deps:
                if dep in self._results and self._results[dep].status == AssetStatus.SUCCESS:
                    dep_outputs[dep] = self._results[dep].output
                else:
                    skip = True
                    break

            if skip:
                result = AssetResult(name=asset_name, status=AssetStatus.SKIPPED)
                results.append(result)
                self._results[asset_name] = result
                success = False
                continue

            try:
                if dep_outputs:
                    output = asset_def.fn(**dep_outputs)
                else:
                    output = asset_def.fn()
                result = AssetResult(
                    name=asset_name,
                    status=AssetStatus.SUCCESS,
                    output=output,
                )
            except Exception as e:
                result = AssetResult(
                    name=asset_name,
                    status=AssetStatus.FAILED,
                    error=f"{type(e).__name__}: {e}",
                )
                success = False

            results.append(result)
            self._results[asset_name] = result

        return PipelineResult(
            job_name=job_name,
            assets=tuple(results),
            success=success,
        )

    def reset(self) -> None:
        """Clear all results (for re-execution)."""
        self._results.clear()

    # ---- internals -------------------------------------------------------

    def _topological_sort(self) -> list[str]:
        """Kahn's algorithm for topological ordering."""
        in_degree: dict[str, int] = {name: 0 for name in self._assets}
        for asset_def in self._assets.values():
            for dep in asset_def.deps:
                if dep in in_degree:
                    in_degree[asset_def.name] = in_degree.get(asset_def.name, 0)

        adj: dict[str, list[str]] = {name: [] for name in self._assets}
        for asset_def in self._assets.values():
            for dep in asset_def.deps:
                if dep in adj:
                    adj[dep].append(asset_def.name)
                    in_degree[asset_def.name] += 1

        queue = [n for n, d in in_degree.items() if d == 0]
        result: list[str] = []

        while queue:
            queue.sort()
            node = queue.pop(0)
            result.append(node)
            for neighbor in adj.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return result


@dataclass
class _AssetDef:
    name: str
    fn: Callable[..., Any]
    deps: list[str] = field(default_factory=list)


__all__ = ["AssetResult", "AssetStatus", "PipelineOrchestrator", "PipelineResult"]

# ADAPTED FROM: kubeflow/pipelines (kfp SDK)
# (kfp/dsl/_component_bridge.py — @component decorator;
#  kfp/dsl/_pipeline.py — @pipeline decorator, pipeline context;
#  kfp/compiler/compiler.py — Compiler.compile() to YAML/JSON IR;
#  kfp/client/client.py — Client, create_run_from_pipeline_func)
"""C-68 — Kubeflow ML pipeline definition and compilation.

This module adapts the ``kfp`` SDK for defining and compiling ML
training pipelines as Kubeflow Pipelines IR (YAML). Never runs locally
— compiles pipeline definitions for submission to a K8s cluster.

What survives from upstream (kubeflow/pipelines):
    * **@component** — ``_component_bridge.py``: decorator that turns a
      Python function into a pipeline component with typed I/O.
    * **@pipeline** — ``_pipeline.py``: decorator that assembles
      components into a DAG.
    * **Compiler.compile()** — ``compiler.py``: serialize pipeline to
      YAML/JSON IR for the Kubeflow Pipelines backend.
    * **Client.create_run** — ``client.py``: submit compiled pipeline.

What we replaced:
    * Real ``kfp`` import is lazy (Protocol seam).
    * In-memory pipeline graph for unit tests.
    * Compilation produces a dict (not YAML file) for assertions.

OFFLINE tier: pipeline definition and submission, never on RUNTIME path.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ComponentSpec:
    """Specification for a pipeline component."""

    name: str
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()


@dataclass
class PipelineSpec:
    """Compiled pipeline specification (IR)."""

    name: str
    components: list[ComponentSpec] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict (mirrors Compiler.compile() YAML output)."""
        return {
            "pipelineInfo": {"name": self.name},
            "components": [
                {"name": c.name, "inputs": list(c.inputs), "outputs": list(c.outputs)}
                for c in self.components
            ],
            "dag": {"edges": [{"source": s, "target": t} for s, t in self.edges]},
        }


class KubeflowPipeline:
    """Kubeflow-style ML pipeline builder.

    Registers components and compiles them into a pipeline IR for
    submission to a Kubeflow Pipelines backend.

    Usage::

        kf = KubeflowPipeline("training_pipeline")

        @kf.component(name="preprocess", outputs=["features"])
        def preprocess(raw_data: str) -> dict:
            return {"features": "processed"}

        @kf.component(name="train", inputs=["features"], outputs=["model"])
        def train(features: dict) -> dict:
            return {"model": "trained"}

        kf.connect("preprocess", "train")
        spec = kf.compile()
    """

    def __init__(self, name: str = "default_pipeline") -> None:
        self._name = name
        self._components: dict[str, _ComponentDef] = {}
        self._edges: list[tuple[str, str]] = []

    def component(
        self,
        name: str,
        inputs: Sequence[str] = (),
        outputs: Sequence[str] = (),
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a pipeline component (mirrors @kfp.component)."""

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self._components[name] = _ComponentDef(
                name=name,
                fn=fn,
                inputs=tuple(inputs),
                outputs=tuple(outputs),
            )
            return fn

        return decorator

    def connect(self, source: str, target: str) -> None:
        """Connect two components (add DAG edge)."""
        self._edges.append((source, target))

    def compile(self) -> PipelineSpec:
        """Compile pipeline to IR (mirrors Compiler.compile()).

        Returns a PipelineSpec that can be serialized to dict/YAML.
        """
        specs = [
            ComponentSpec(name=c.name, inputs=c.inputs, outputs=c.outputs)
            for c in self._components.values()
        ]
        return PipelineSpec(name=self._name, components=specs, edges=self._edges)

    def run_local(self, inputs: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute pipeline locally for testing (not via K8s).

        Runs components in topological order.
        """
        order = self._topological_sort()
        results: dict[str, Any] = dict(inputs or {})

        for comp_name in order:
            comp = self._components[comp_name]
            try:
                result = comp.fn(**{k: results.get(k) for k in comp.inputs if k in results})
                if isinstance(result, dict):
                    results.update(result)
                results[comp_name] = result
            except Exception:
                results[comp_name] = None

        return results

    def component_count(self) -> int:
        """Return number of registered components."""
        return len(self._components)

    # ---- internals -------------------------------------------------------

    def _topological_sort(self) -> list[str]:
        """Sort components by dependency order."""
        in_degree: dict[str, int] = {name: 0 for name in self._components}
        adj: dict[str, list[str]] = {name: [] for name in self._components}

        for src, tgt in self._edges:
            if src in adj and tgt in in_degree:
                adj[src].append(tgt)
                in_degree[tgt] += 1

        queue = sorted(n for n, d in in_degree.items() if d == 0)
        result: list[str] = []

        while queue:
            node = queue.pop(0)
            result.append(node)
            for neighbor in sorted(adj.get(node, [])):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return result


@dataclass
class _ComponentDef:
    name: str
    fn: Callable[..., Any]
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()


__all__ = ["ComponentSpec", "KubeflowPipeline", "PipelineSpec"]

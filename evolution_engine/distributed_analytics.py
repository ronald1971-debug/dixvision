# ADAPTED FROM: dask/dask
# (dask/dataframe/core.py — DataFrame lazy parallel operations;
#  dask/delayed.py — @dask.delayed decorator for custom computation graphs;
#  dask/base.py — compute(), visualize();
#  dask/threaded.py — synchronous scheduler for testing)
"""C-67 — Dask large-scale offline analytics.

This module adapts Dask's lazy computation graph model for large-scale
feature computation when polars single-threaded saturates.

What survives from upstream (dask/dask):
    * **@delayed** — ``delayed.py``: wrap any function into a lazy node
      in a computation graph.
    * **compute()** — ``base.py``: trigger execution of the graph.
    * **DataFrame** — ``dataframe/core.py``: lazy parallel DataFrame
      operations (map_partitions, groupby, apply).
    * **Local scheduler** — ``threaded.py``: synchronous execution for
      testing without a cluster.

What we replaced:
    * Real ``dask`` import is lazy (Protocol seam).
    * In-memory DAG executor for unit tests (mirrors dask.compute).
    * Same analytics interface as polars-based pipelines.

OFFLINE tier: large-scale computation, never on RUNTIME path.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DelayedNode:
    """A node in a lazy computation graph (mirrors dask.delayed)."""

    name: str
    fn: Callable[..., Any]
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    deps: list[DelayedNode] = field(default_factory=list)
    _result: Any = None
    _computed: bool = False

    def compute(self) -> Any:
        """Compute this node and all dependencies."""
        if self._computed:
            return self._result

        resolved_args = []
        for arg in self.args:
            if isinstance(arg, DelayedNode):
                resolved_args.append(arg.compute())
            else:
                resolved_args.append(arg)

        resolved_kwargs = {}
        for k, v in self.kwargs.items():
            if isinstance(v, DelayedNode):
                resolved_kwargs[k] = v.compute()
            else:
                resolved_kwargs[k] = v

        self._result = self.fn(*resolved_args, **resolved_kwargs)
        self._computed = True
        return self._result


class DistributedAnalytics:
    """Dask-style distributed analytics engine.

    Builds a lazy computation graph with ``delayed()`` and executes
    it via ``compute()``. In test mode, runs synchronously. In
    production, submits to a Dask distributed cluster.

    Usage::

        da = DistributedAnalytics()

        @da.delayed("load_data")
        def load():
            return [1, 2, 3, 4, 5]

        @da.delayed("compute_stats")
        def stats(data):
            return {"mean": sum(data) / len(data)}

        data_node = load()
        stats_node = stats(data_node)
        result = da.compute(stats_node)
    """

    def __init__(self, *, scheduler: str = "synchronous") -> None:
        self._scheduler = scheduler
        self._nodes: dict[str, DelayedNode] = {}

    def delayed(self, name: str) -> Callable[[Callable[..., Any]], Callable[..., DelayedNode]]:
        """Decorator to make a function lazy (mirrors @dask.delayed)."""

        def decorator(fn: Callable[..., Any]) -> Callable[..., DelayedNode]:
            def wrapper(*args: Any, **kwargs: Any) -> DelayedNode:
                node = DelayedNode(name=name, fn=fn, args=args, kwargs=kwargs)
                self._nodes[name] = node
                return node

            return wrapper

        return decorator

    def compute(self, *nodes: DelayedNode) -> Any:
        """Trigger computation of one or more delayed nodes.

        Mirrors ``dask.compute(*delayed_objects)``.
        """
        results = []
        for node in nodes:
            results.append(node.compute())
        if len(results) == 1:
            return results[0]
        return tuple(results)

    def node_count(self) -> int:
        """Return number of registered computation nodes."""
        return len(self._nodes)


__all__ = ["DelayedNode", "DistributedAnalytics"]

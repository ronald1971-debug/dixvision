"""evolution_engine.dyon.dependency_graph — DependencyGraph.

Full import dependency graph over the Python source tree.
Builds on the edge list produced by RepoInspector to provide:

  - Directed intra-repo graph (source → target, module-level)
  - Cycle detection — iterative DFS back-edge detection
  - B1 authority boundary violation detection (e.g. cognitive layers → execution_engine)
  - Isolation detection (no in-edges AND no out-edges within repo)

The scan is driven at REPO_INSPECT_INTERVAL cadence via DyonEngineeringRuntime
after RepoInspector has already produced its edge list, so this adds analysis
with no additional file I/O.

Authority (L2/B1): evolution_engine.* and standard library only.
INV-15: ts_ns is caller-supplied; no wall-clock reads.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

_logger = logging.getLogger(__name__)

# Packages that must not be imported by higher-level cognitive/governance layers
_B1_FORBIDDEN_TARGETS: frozenset[str] = frozenset({
    "execution_engine",
    "execution",
})
# Packages considered "upper layers" that must not directly import execution
_B1_UPPER_LAYERS: frozenset[str] = frozenset({
    "intelligence_engine",
    "mind",
    "learning_engine",
    "evolution_engine",
    "governance_engine",
    "cognitive_governance",
})


@dataclass(frozen=True, slots=True)
class Cycle:
    """One detected import cycle."""

    path: tuple[str, ...]
    length: int
    involves_layer: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": list(self.path),
            "length": self.length,
            "involves_layer": self.involves_layer,
        }


@dataclass(frozen=True, slots=True)
class B1Violation:
    """One detected B1 authority boundary violation."""

    source_module: str
    target_package: str
    source_layer: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_module": self.source_module,
            "target_package": self.target_package,
            "source_layer": self.source_layer,
            "description": self.description,
        }


@dataclass
class DependencyGraphSnapshot:
    """One complete dependency graph analysis snapshot."""

    ts_ns: int = 0
    total_modules: int = 0
    total_edges: int = 0
    cycles: list[Cycle] = field(default_factory=list)
    b1_violations: list[B1Violation] = field(default_factory=list)
    isolated_modules: list[str] = field(default_factory=list)
    scan_duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts_ns": self.ts_ns,
            "total_modules": self.total_modules,
            "total_edges": self.total_edges,
            "cycle_count": len(self.cycles),
            "cycles": [c.to_dict() for c in self.cycles[:20]],
            "b1_violation_count": len(self.b1_violations),
            "b1_violations": [v.to_dict() for v in self.b1_violations[:20]],
            "isolated_module_count": len(self.isolated_modules),
            "isolated_modules": self.isolated_modules[:20],
            "scan_duration_ms": round(self.scan_duration_ms, 2),
        }


class DependencyGraph:
    """Import dependency graph analyzer for DYON.

    Builds on RepoInspector's edge list and adds cycle detection and
    B1 authority violation detection without re-reading the filesystem.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot: DependencyGraphSnapshot | None = None
        self._scan_count: int = 0

    def scan(self, ts_ns: int) -> DependencyGraphSnapshot:
        """Build the dependency graph from the latest RepoInspector snapshot.

        If no inspector data is available, returns an empty snapshot.
        """
        import time as _time
        t0 = _time.monotonic()

        edges: list[tuple[str, str]] = []
        modules: list[Any] = []
        layer_map: dict[str, str] = {}

        try:
            from evolution_engine.dyon.repo_inspector import get_repo_inspector
            repo_snap = get_repo_inspector().latest_snapshot()
            if repo_snap is not None:
                edges = list(repo_snap.edge_list)
                modules = list(repo_snap.modules)
                for m in modules:
                    layer_map[m.module_path] = m.layer
        except Exception:
            pass

        repo_modules: set[str] = {m.module_path for m in modules}

        # Restrict to intra-repo source nodes only
        intra_edges: list[tuple[str, str]] = [
            (src, tgt) for src, tgt in edges if src in repo_modules
        ]

        # Build adjacency for DFS
        adj: dict[str, list[str]] = defaultdict(list)
        for src, tgt in intra_edges:
            adj[src].append(tgt)

        cycles = self._detect_cycles(adj, repo_modules, layer_map)
        b1_violations = self._detect_b1_violations(intra_edges, layer_map)

        # Isolated: no in-edges AND no out-edges among repo modules
        sources = {s for s, _ in intra_edges}
        intra_targets = {t for _, t in intra_edges if t in repo_modules}
        isolated = sorted(
            m for m in repo_modules
            if m not in sources and m not in intra_targets
        )

        duration_ms = (_time.monotonic() - t0) * 1000.0
        snap = DependencyGraphSnapshot(
            ts_ns=ts_ns,
            total_modules=len(modules),
            total_edges=len(intra_edges),
            cycles=cycles[:50],
            b1_violations=b1_violations[:50],
            isolated_modules=isolated,
            scan_duration_ms=duration_ms,
        )

        with self._lock:
            self._snapshot = snap
            self._scan_count += 1

        if b1_violations:
            self._emit_b1_violations(b1_violations, ts_ns)

        _logger.info(
            "DependencyGraph: %d modules, %d edges, %d cycles, %d B1 violations in %.0fms",
            len(modules), len(intra_edges), len(cycles), len(b1_violations), duration_ms,
        )
        return snap

    def latest_snapshot(self) -> DependencyGraphSnapshot | None:
        with self._lock:
            return self._snapshot

    def snapshot_dict(self) -> dict[str, Any]:
        with self._lock:
            snap = self._snapshot
        if snap is None:
            return {
                "status": "no_scan_yet",
                "total_modules": 0,
                "total_edges": 0,
                "cycle_count": 0,
                "b1_violation_count": 0,
            }
        return snap.to_dict()

    @property
    def scan_count(self) -> int:
        with self._lock:
            return self._scan_count

    # ------------------------------------------------------------------
    # Cycle detection — iterative DFS
    # ------------------------------------------------------------------

    def _detect_cycles(
        self,
        adj: dict[str, list[str]],
        nodes: set[str],
        layer_map: dict[str, str],
    ) -> list[Cycle]:
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {n: WHITE for n in nodes}
        parent: dict[str, str | None] = {n: None for n in nodes}
        cycles: list[Cycle] = []
        seen_keys: set[frozenset[str]] = set()

        def _reconstruct(start: str, end: str) -> tuple[str, ...]:
            path = [end]
            cur = end
            limit = len(nodes)
            while cur != start and limit > 0:
                p = parent.get(cur)
                if p is None or p in path:
                    break
                path.append(p)
                cur = p
                limit -= 1
            path.append(start)
            path.reverse()
            return tuple(path)

        for root in list(nodes):
            if color.get(root, WHITE) != WHITE:
                continue
            stack: list[tuple[str, int]] = [(root, 0)]
            color[root] = GRAY
            while stack and len(cycles) < 50:
                node, idx = stack[-1]
                neighbors = adj.get(node, [])
                if idx >= len(neighbors):
                    color[node] = BLACK
                    stack.pop()
                    continue
                stack[-1] = (node, idx + 1)
                nbr = neighbors[idx]
                if nbr not in nodes:
                    continue
                c = color.get(nbr, WHITE)
                if c == GRAY:
                    path = _reconstruct(nbr, node)
                    key = frozenset(path)
                    if key not in seen_keys:
                        seen_keys.add(key)
                        cycles.append(Cycle(
                            path=path,
                            length=len(path),
                            involves_layer=layer_map.get(path[0], "?"),
                        ))
                elif c == WHITE:
                    color[nbr] = GRAY
                    parent[nbr] = node
                    stack.append((nbr, 0))

        return cycles

    # ------------------------------------------------------------------
    # B1 violation detection
    # ------------------------------------------------------------------

    def _detect_b1_violations(
        self,
        edges: list[tuple[str, str]],
        layer_map: dict[str, str],
    ) -> list[B1Violation]:
        violations: list[B1Violation] = []
        seen: set[tuple[str, str]] = set()
        for src, tgt_pkg in edges:
            if tgt_pkg not in _B1_FORBIDDEN_TARGETS:
                continue
            src_pkg = src.split(".")[0]
            if src_pkg not in _B1_UPPER_LAYERS:
                continue
            key = (src, tgt_pkg)
            if key in seen:
                continue
            seen.add(key)
            src_layer = layer_map.get(src, "?")
            violations.append(B1Violation(
                source_module=src,
                target_package=tgt_pkg,
                source_layer=src_layer,
                description=(
                    f"B1 violation: {src} ({src_layer}) imports "
                    f"{tgt_pkg} — cognitive/governance layers must not "
                    "directly import execution_engine"
                ),
            ))
        return violations

    def _emit_b1_violations(
        self, violations: list[B1Violation], ts_ns: int
    ) -> None:
        try:
            from evolution_engine.charter.dyon_observability_emitter import (
                emit_dependency_anomaly,
            )
            for v in violations[:5]:
                emit_dependency_anomaly(
                    ts_ns=ts_ns,
                    source_module=v.source_module,
                    target_module=v.target_package,
                    anomaly_kind="FORBIDDEN",
                    severity="CRITICAL",
                    description=v.description,
                )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_graph: DependencyGraph | None = None
_graph_lock = threading.Lock()


def get_dependency_graph() -> DependencyGraph:
    """Return the process-wide DependencyGraph singleton."""
    global _graph
    with _graph_lock:
        if _graph is None:
            _graph = DependencyGraph()
    return _graph


__all__ = [
    "B1Violation",
    "Cycle",
    "DependencyGraph",
    "DependencyGraphSnapshot",
    "get_dependency_graph",
]

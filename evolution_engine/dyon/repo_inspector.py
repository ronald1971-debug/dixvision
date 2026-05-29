"""evolution_engine.dyon.repo_inspector — RepoInspector.

DYON's repository structure intelligence.  Walks the Python source tree,
builds a module map and import edge list, infers layer assignments from
directory prefixes, and identifies structurally isolated modules.

The inspector is intentionally lightweight — it does NOT run a full AST
analysis on every tick (that is the topology_scanner's job).  Instead it
scans filenames and performs a single-pass regex sweep for top-level import
lines to build the edge list.

Layer assignment (approximate, from directory prefix):
  L0  core/contracts/
  L1  state/
  L2  governance_engine/
  L3  intelligence_engine/
  L4  execution_engine/
  L5  learning_engine/
  L6  system_engine/ system/
  L7  evolution_engine/
  L8  simulation/
  UI  ui/ dashboard2026/
  SVC runtime/ observability/
  ?   everything else

Results are cached between runs.  Re-scan only when `scan()` is called
explicitly (driven by DyonEngineeringRuntime at a slow cadence).

Authority (L2/B1): evolution_engine.* and standard library only.
INV-15: No wall-clock reads inside any method.
"""

from __future__ import annotations

import logging
import pathlib
import re
import threading
from dataclasses import dataclass, field
from typing import Any

_logger = logging.getLogger(__name__)

_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.MULTILINE
)

# Layer prefix map — ordered: first match wins
_LAYER_PREFIXES: tuple[tuple[str, str], ...] = (
    ("core", "L0"),
    ("state", "L1"),
    ("governance_engine", "L2"),
    ("cognitive_governance", "L2"),
    ("intelligence_engine", "L3"),
    ("execution_engine", "L4"),
    ("learning_engine", "L5"),
    ("system_engine", "L6"),
    ("system", "L6"),
    ("evolution_engine", "L7"),
    ("simulation", "L8"),
    ("ui", "UI"),
    ("dashboard2026", "UI"),
    ("runtime", "SVC"),
    ("observability", "SVC"),
    ("trader_modeling", "L3"),
    ("mind", "L3"),
)

_EXCLUDED_DIRS: frozenset[str] = frozenset({
    ".git", "__pycache__", ".venv", "venv", "node_modules",
    ".mypy_cache", ".pytest_cache", "dist", "build", ".tox",
})


def _layer_of(rel_path: str) -> str:
    first_dir = rel_path.split("/")[0] if "/" in rel_path else rel_path
    for prefix, layer in _LAYER_PREFIXES:
        if first_dir == prefix or first_dir.startswith(prefix):
            return layer
    return "?"


# ---------------------------------------------------------------------------
# Data records
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ModuleInfo:
    """One discovered Python module."""

    module_path: str        # dot-notation module path, e.g. "state.event_bus"
    rel_file: str           # repo-relative file path, e.g. "state/event_bus.py"
    layer: str              # L0–L8 / UI / SVC / ?
    line_count: int
    import_count: int       # number of import statements found


@dataclass
class RepoSnapshot:
    """One complete repository structure snapshot."""

    ts_ns: int = 0
    root: str = "."
    total_files: int = 0
    total_lines: int = 0
    layer_counts: dict[str, int] = field(default_factory=dict)
    modules: list[ModuleInfo] = field(default_factory=list)
    edge_list: list[tuple[str, str]] = field(default_factory=list)  # (from, to) module pairs
    isolated_modules: list[str] = field(default_factory=list)       # no in- or out-edges
    edge_count: int = 0
    scan_duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        layer_dist = dict(sorted(self.layer_counts.items()))
        top_connected = sorted(
            set(m for m, _ in self.edge_list) | set(m for _, m in self.edge_list),
            key=lambda m: -sum(1 for a, b in self.edge_list if a == m or b == m),
        )[:10]
        return {
            "ts_ns": self.ts_ns,
            "root": self.root,
            "total_files": self.total_files,
            "total_lines": self.total_lines,
            "layer_distribution": layer_dist,
            "edge_count": self.edge_count,
            "isolated_module_count": len(self.isolated_modules),
            "isolated_modules": self.isolated_modules[:20],
            "top_connected_modules": top_connected,
            "scan_duration_ms": round(self.scan_duration_ms, 2),
        }


# ---------------------------------------------------------------------------
# RepoInspector
# ---------------------------------------------------------------------------


class RepoInspector:
    """Lightweight repository structure inspector for DYON.

    Args:
        repo_root: Path to the repository root.
        max_edge_per_file: Limit edges collected per file (avoids huge graphs).
    """

    def __init__(
        self,
        *,
        repo_root: str | pathlib.Path = ".",
        max_edges_per_file: int = 20,
    ) -> None:
        self._root = pathlib.Path(repo_root).resolve()
        self._max_edges = max(5, max_edges_per_file)
        self._lock = threading.Lock()
        self._snapshot: RepoSnapshot | None = None
        self._scan_count: int = 0

    # ------------------------------------------------------------------
    # Primary scan
    # ------------------------------------------------------------------

    def scan(self, ts_ns: int) -> RepoSnapshot:
        """Walk the repository and build a fresh snapshot.

        This is intentionally O(files × lines) — call at slow cadence only.
        Returns the new snapshot.
        """
        import time as _time
        t0 = _time.monotonic()

        modules: list[ModuleInfo] = []
        edges: list[tuple[str, str]] = []
        layer_counts: dict[str, int] = {}
        total_lines = 0

        for py_file in self._iter_python_files():
            try:
                rel = py_file.relative_to(self._root)
                rel_str = rel.as_posix()
                layer = _layer_of(rel_str)
                layer_counts[layer] = layer_counts.get(layer, 0) + 1

                source = py_file.read_text(encoding="utf-8", errors="ignore")
                lines = source.count("\n") + 1
                total_lines += lines

                module_path = rel_str.replace("/", ".").removesuffix(".py")
                if module_path.endswith(".__init__"):
                    module_path = module_path[: -len(".__init__")]

                # Collect import edges (single-pass regex, fast)
                file_edges: list[tuple[str, str]] = []
                for m in _IMPORT_RE.finditer(source):
                    imported = m.group(1) or m.group(2) or ""
                    imported = imported.split(".")[0]  # top-level package only
                    if imported and imported != module_path.split(".")[0]:
                        file_edges.append((module_path, imported))
                    if len(file_edges) >= self._max_edges:
                        break

                import_count = len(file_edges)
                edges.extend(file_edges)
                modules.append(ModuleInfo(
                    module_path=module_path,
                    rel_file=rel_str,
                    layer=layer,
                    line_count=lines,
                    import_count=import_count,
                ))
            except Exception:
                continue

        # Find isolated modules (no edges in or out)
        edge_sources = {a for a, _ in edges}
        edge_targets = {b for _, b in edges}
        connected = edge_sources | edge_targets
        isolated = [
            m.module_path for m in modules
            if m.module_path not in connected and m.module_path not in edge_targets
        ]

        duration_ms = (_time.monotonic() - t0) * 1000.0
        snap = RepoSnapshot(
            ts_ns=ts_ns,
            root=str(self._root),
            total_files=len(modules),
            total_lines=total_lines,
            layer_counts=layer_counts,
            modules=modules,
            edge_list=edges[:5000],   # cap for memory safety
            isolated_modules=sorted(isolated),
            edge_count=len(edges),
            scan_duration_ms=duration_ms,
        )

        with self._lock:
            self._snapshot = snap
            self._scan_count += 1

        _logger.info(
            "RepoInspector: scanned %d files, %d edges, %d isolated in %.0fms",
            len(modules), len(edges), len(isolated), duration_ms,
        )
        return snap

    # ------------------------------------------------------------------
    # Read surface
    # ------------------------------------------------------------------

    def latest_snapshot(self) -> RepoSnapshot | None:
        with self._lock:
            return self._snapshot

    @property
    def scan_count(self) -> int:
        with self._lock:
            return self._scan_count

    def snapshot_dict(self) -> dict[str, Any]:
        with self._lock:
            snap = self._snapshot
        if snap is None:
            return {
                "status": "no_scan_yet",
                "total_files": 0,
                "layer_distribution": {},
                "edge_count": 0,
                "isolated_module_count": 0,
            }
        return snap.to_dict()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _iter_python_files(self):
        """Yield all .py files under the repo root, skipping excluded dirs."""
        for item in self._root.rglob("*.py"):
            try:
                # Skip excluded directories
                parts = item.parts
                if any(p in _EXCLUDED_DIRS for p in parts):
                    continue
                yield item
            except Exception:
                continue


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_inspector: RepoInspector | None = None
_inspector_lock = threading.Lock()


def get_repo_inspector(*, repo_root: str | pathlib.Path = ".") -> RepoInspector:
    """Return the process-wide RepoInspector singleton."""
    global _inspector
    with _inspector_lock:
        if _inspector is None:
            _inspector = RepoInspector(repo_root=repo_root)
    return _inspector


__all__ = [
    "ModuleInfo",
    "RepoInspector",
    "RepoSnapshot",
    "get_repo_inspector",
]

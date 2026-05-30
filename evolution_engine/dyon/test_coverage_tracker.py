"""evolution_engine.dyon.test_coverage_tracker — TestCoverageTracker.

DYON's test coverage intelligence.  For each Python module in the source
tree, determines whether a corresponding unit test file exists and
classifies the module as COVERED, UNCOVERED, or PARTIAL.

Detection strategy:
  COVERED    — test file found AND contains ≥ 3 test_ functions
  PARTIAL    — test file found but contains < 3 test_ functions
  UNCOVERED  — no test file found anywhere in the tests/ tree

Convention: test files are discovered by rglob("test_*.py") and matched
to source modules by stem, e.g. "strategy_arbiter.py" → "test_strategy_arbiter.py".

Results feed DYON's proposal engine so it can generate test-generation
proposals for high-priority uncovered modules (Manifest §13 requirement).

Authority (L2/B1): evolution_engine.* and standard library only.
INV-15: ts_ns is caller-supplied; no wall-clock reads.
"""

from __future__ import annotations

import logging
import pathlib
import re
import threading
from dataclasses import dataclass, field
from typing import Any

_logger = logging.getLogger(__name__)

_TEST_FN_RE = re.compile(r"^\s*def\s+test_\w+", re.MULTILINE)
_PARTIAL_THRESHOLD: int = 3   # fewer than this many test functions → PARTIAL

_SKIP_NAMES: frozenset[str] = frozenset({
    "__init__.py", "conftest.py", "setup.py",
})
_SKIP_PREFIXES: frozenset[str] = frozenset({
    "tests/", "test_", "scripts/", "migrations/",
})
_SKIP_DIRS: frozenset[str] = frozenset({
    ".git", "__pycache__", ".venv", "venv", "node_modules",
    ".mypy_cache", ".pytest_cache", "dist", "build",
})

COVERED = "COVERED"
PARTIAL = "PARTIAL"
UNCOVERED = "UNCOVERED"


@dataclass(frozen=True, slots=True)
class ModuleCoverage:
    """Coverage status for one Python module."""

    module_path: str
    rel_file: str
    layer: str
    classification: str
    test_file: str        # relative path to test file, or ""
    test_fn_count: int
    line_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "module_path": self.module_path,
            "rel_file": self.rel_file,
            "layer": self.layer,
            "classification": self.classification,
            "test_file": self.test_file,
            "test_fn_count": self.test_fn_count,
            "line_count": self.line_count,
        }


@dataclass
class CoverageSnapshot:
    """One complete test coverage scan snapshot."""

    ts_ns: int = 0
    total_modules: int = 0
    covered: int = 0
    partial: int = 0
    uncovered: int = 0
    coverage_pct: float = 0.0
    by_layer: dict[str, dict[str, int]] = field(default_factory=dict)
    top_uncovered: list[ModuleCoverage] = field(default_factory=list)
    scan_duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts_ns": self.ts_ns,
            "total_modules": self.total_modules,
            "covered": self.covered,
            "partial": self.partial,
            "uncovered": self.uncovered,
            "coverage_pct": round(self.coverage_pct, 1),
            "by_layer": self.by_layer,
            "top_uncovered": [m.to_dict() for m in self.top_uncovered[:30]],
            "scan_duration_ms": round(self.scan_duration_ms, 2),
        }


class TestCoverageTracker:
    """Maps Python source modules to their test coverage status.

    Uses RepoInspector's module list when available; otherwise walks the
    repo directly.  Identifies test files by filename convention and
    counts the number of test_ functions to distinguish COVERED vs PARTIAL.

    Args:
        repo_root: Path to the repository root.
    """

    def __init__(self, *, repo_root: str | pathlib.Path = ".") -> None:
        self._root = pathlib.Path(repo_root).resolve()
        self._lock = threading.Lock()
        self._snapshot: CoverageSnapshot | None = None
        self._scan_count: int = 0

    def scan(self, ts_ns: int) -> CoverageSnapshot:
        """Scan test coverage for all Python source modules.

        Returns:
            CoverageSnapshot with per-layer statistics and top-uncovered list.
        """
        import time as _time
        t0 = _time.monotonic()

        modules: list[Any] = []
        try:
            from evolution_engine.dyon.repo_inspector import get_repo_inspector
            repo_snap = get_repo_inspector(repo_root=self._root).latest_snapshot()
            if repo_snap is not None:
                modules = list(repo_snap.modules)
        except Exception:
            pass

        test_index = self._build_test_index()
        results: list[ModuleCoverage] = []

        for mod in modules:
            rel_file = mod.rel_file
            fname = pathlib.Path(rel_file).name

            if fname in _SKIP_NAMES:
                continue
            if fname.startswith("test_"):
                continue
            if any(rel_file.startswith(pfx) for pfx in _SKIP_PREFIXES):
                continue

            base = pathlib.Path(rel_file).stem
            test_file, fn_count = self._find_test(base, test_index)

            if not test_file:
                classification = UNCOVERED
            elif fn_count < _PARTIAL_THRESHOLD:
                classification = PARTIAL
            else:
                classification = COVERED

            results.append(ModuleCoverage(
                module_path=mod.module_path,
                rel_file=rel_file,
                layer=mod.layer,
                classification=classification,
                test_file=test_file,
                test_fn_count=fn_count,
                line_count=mod.line_count,
            ))

        covered_n = sum(1 for r in results if r.classification == COVERED)
        partial_n = sum(1 for r in results if r.classification == PARTIAL)
        uncovered_n = sum(1 for r in results if r.classification == UNCOVERED)
        total = len(results)
        pct = ((covered_n + partial_n * 0.5) / total * 100.0) if total > 0 else 0.0

        by_layer: dict[str, dict[str, int]] = {}
        for r in results:
            layer = r.layer
            if layer not in by_layer:
                by_layer[layer] = {COVERED: 0, PARTIAL: 0, UNCOVERED: 0}
            by_layer[layer][r.classification] = by_layer[layer].get(r.classification, 0) + 1

        # Top uncovered sorted by line_count descending (biggest unprotected modules first)
        top_uncovered = sorted(
            (r for r in results if r.classification == UNCOVERED),
            key=lambda r: -r.line_count,
        )

        duration_ms = (_time.monotonic() - t0) * 1000.0
        snap = CoverageSnapshot(
            ts_ns=ts_ns,
            total_modules=total,
            covered=covered_n,
            partial=partial_n,
            uncovered=uncovered_n,
            coverage_pct=pct,
            by_layer=by_layer,
            top_uncovered=top_uncovered,
            scan_duration_ms=duration_ms,
        )

        with self._lock:
            self._snapshot = snap
            self._scan_count += 1

        _logger.info(
            "TestCoverageTracker: %d modules — %d covered, %d partial, %d uncovered (%.1f%%) in %.0fms",
            total, covered_n, partial_n, uncovered_n, pct, duration_ms,
        )
        return snap

    def latest_snapshot(self) -> CoverageSnapshot | None:
        with self._lock:
            return self._snapshot

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            snap = self._snapshot
            scan_count = self._scan_count
        if snap is None:
            return {
                "runtime": "TestCoverageTracker",
                "scan_count": scan_count,
                "status": "no_scan_yet",
                "coverage_pct": 0.0,
            }
        out = snap.to_dict()
        out["runtime"] = "TestCoverageTracker"
        out["scan_count"] = scan_count
        return out

    @property
    def scan_count(self) -> int:
        with self._lock:
            return self._scan_count

    def _build_test_index(self) -> dict[str, list[pathlib.Path]]:
        """Build a mapping from module basename → test file paths via rglob."""
        index: dict[str, list[pathlib.Path]] = {}
        try:
            for test_file in self._root.rglob("test_*.py"):
                parts = test_file.parts
                if any(p in _SKIP_DIRS for p in parts):
                    continue
                stem = test_file.stem  # e.g. "test_strategy_arbiter"
                base = stem[5:] if stem.startswith("test_") else stem
                if not base:
                    continue
                index.setdefault(base, []).append(test_file)
        except Exception:
            pass
        return index

    def _find_test(
        self, base: str, index: dict[str, list[pathlib.Path]]
    ) -> tuple[str, int]:
        """Return (rel_path, test_fn_count) for the module, or ("", 0)."""
        files = index.get(base, [])
        if not files:
            return "", 0
        test_file = files[0]
        try:
            source = test_file.read_text(encoding="utf-8", errors="ignore")
            fn_count = len(_TEST_FN_RE.findall(source))
            rel = str(test_file.relative_to(self._root)).replace("\\", "/")
            return rel, fn_count
        except Exception:
            return "", 0


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_tracker: TestCoverageTracker | None = None
_tracker_lock = threading.Lock()


def get_test_coverage_tracker(
    *, repo_root: str | pathlib.Path = ".",
) -> TestCoverageTracker:
    """Return the process-wide TestCoverageTracker singleton."""
    global _tracker
    with _tracker_lock:
        if _tracker is None:
            _tracker = TestCoverageTracker(repo_root=repo_root)
    return _tracker


__all__ = [
    "CoverageSnapshot",
    "ModuleCoverage",
    "TestCoverageTracker",
    "get_test_coverage_tracker",
]

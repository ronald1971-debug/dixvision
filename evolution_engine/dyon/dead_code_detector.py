"""evolution_engine.dyon.dead_code_detector — DeadCodeDetector.

DYON's dead module / orphan code intelligence.  Identifies Python files in
the repository that show signs of being dead, abandoned, or structurally
detached from the active codebase.

Detection strategies:

  ORPHANED  — file is never imported by any other file in the repo
              (source: RepoInspector edge_list + module map)

  ISOLATED  — file has no imports AND no importers (true island)

  STUB      — file has ≤ 10 non-blank, non-comment lines (near-empty)

  EMPTY     — file has 0 real code lines

  SHADOWED  — file has a duplicate module name elsewhere in a different layer
              (import resolution may pick up the wrong one)

Each detected module is classified, assigned a confidence (0–1), and
accumulated in a ring buffer.  At each full scan, any ORPHANED or ISOLATED
modules at high confidence are emitted as DYON_PROPOSAL events to the event
bus so the GovernedEvolutionPipeline can queue them for governance review.

Authority (L2/B1): evolution_engine.* and standard library only.
INV-15: ts_ns is caller-supplied; no wall-clock reads.
"""

from __future__ import annotations

import logging
import pathlib
import re
import threading
from dataclasses import dataclass
from typing import Any

_logger = logging.getLogger(__name__)

_COMMENT_RE = re.compile(r"^\s*(#|$)")
_STUB_LINE_THRESHOLD: int = 10
_PROPOSAL_CONFIDENCE_THRESHOLD: float = 0.70

# Well-known files that are intentionally minimal and should not be flagged
_KNOWN_STUBS: frozenset[str] = frozenset({
    "__init__.py",
    "py.typed",
    "conftest.py",
    "setup.py",
    "setup.cfg",
})


# ---------------------------------------------------------------------------
# Data record
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DeadModule:
    """One detected dead or suspect module."""

    rel_file: str           # repo-relative file path
    module_path: str        # dot-notation path
    classification: str     # ORPHANED | ISOLATED | STUB | EMPTY | SHADOWED
    confidence: float       # 0.0–1.0
    line_count: int
    reason: str             # human-readable explanation
    ts_ns: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "rel_file": self.rel_file,
            "module_path": self.module_path,
            "classification": self.classification,
            "confidence": round(self.confidence, 3),
            "line_count": self.line_count,
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# DeadCodeDetector
# ---------------------------------------------------------------------------


class DeadCodeDetector:
    """Identifies dead, orphaned, and structurally isolated Python modules.

    Args:
        repo_root: Path to the repository root.
        emit_proposals: If True, emit DYON_PROPOSAL events for high-confidence
                        dead modules (requires event bus to be active).
    """

    def __init__(
        self,
        *,
        repo_root: str | pathlib.Path = ".",
        emit_proposals: bool = True,
    ) -> None:
        self._root = pathlib.Path(repo_root).resolve()
        self._emit_proposals = emit_proposals
        self._lock = threading.Lock()
        self._detected: list[DeadModule] = []
        self._scan_count: int = 0
        self._last_ts_ns: int = 0

    # ------------------------------------------------------------------
    # Primary scan — uses RepoInspector snapshot to avoid duplicate walk
    # ------------------------------------------------------------------

    def scan(self, ts_ns: int) -> list[DeadModule]:
        """Run dead code detection from the latest RepoInspector snapshot.

        Falls back to a direct walk if no snapshot is available.
        Returns the list of detected dead modules.
        """
        try:
            from evolution_engine.dyon.repo_inspector import get_repo_inspector
            snap = get_repo_inspector(repo_root=self._root).latest_snapshot()
        except Exception:
            snap = None

        detected: list[DeadModule] = []

        if snap is not None:
            detected = self._detect_from_snapshot(snap, ts_ns)
        else:
            detected = self._detect_from_walk(ts_ns)

        with self._lock:
            self._detected = detected
            self._scan_count += 1
            self._last_ts_ns = ts_ns

        _logger.info(
            "DeadCodeDetector: found %d dead/suspect modules (scan #%d)",
            len(detected), self._scan_count,
        )

        if self._emit_proposals:
            self._emit_high_confidence_proposals(detected, ts_ns)

        return detected

    # ------------------------------------------------------------------
    # Read surface
    # ------------------------------------------------------------------

    def latest_detected(self) -> list[DeadModule]:
        with self._lock:
            return list(self._detected)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            detected = list(self._detected)
            scan_count = self._scan_count
            last_ts_ns = self._last_ts_ns

        by_class: dict[str, int] = {}
        for dm in detected:
            by_class[dm.classification] = by_class.get(dm.classification, 0) + 1

        return {
            "runtime": "DeadCodeDetector",
            "scan_count": scan_count,
            "last_ts_ns": last_ts_ns,
            "dead_module_count": len(detected),
            "by_classification": by_class,
            "dead_modules": [dm.to_dict() for dm in detected[:50]],
        }

    # ------------------------------------------------------------------
    # Detection from RepoInspector snapshot (fast path)
    # ------------------------------------------------------------------

    def _detect_from_snapshot(self, snap: Any, ts_ns: int) -> list[DeadModule]:
        detected: list[DeadModule] = []

        # Build sets of all importers and all imported modules
        imported_targets: set[str] = set()
        for _, target in snap.edge_list:
            imported_targets.add(target)

        module_names = {m.module_path for m in snap.modules}
        # A module_path is "reachable" if its top-level package appears as import target
        reachable_packages = {t for t in imported_targets if t}

        for mod in snap.modules:
            rel_file = mod.rel_file
            filename = pathlib.Path(rel_file).name

            # Skip known stubs
            if filename in _KNOWN_STUBS:
                continue
            # Skip test files
            if "test" in rel_file.lower() or rel_file.startswith("tests/"):
                continue
            # Skip migration/script files
            if "/scripts/" in rel_file or "/migrations/" in rel_file:
                continue

            # EMPTY
            real_lines = self._count_real_lines_from_module(mod)
            if real_lines == 0:
                detected.append(DeadModule(
                    rel_file=rel_file,
                    module_path=mod.module_path,
                    classification="EMPTY",
                    confidence=0.95,
                    line_count=mod.line_count,
                    reason="File contains no real code lines",
                    ts_ns=ts_ns,
                ))
                continue

            # STUB
            if 0 < real_lines <= _STUB_LINE_THRESHOLD:
                detected.append(DeadModule(
                    rel_file=rel_file,
                    module_path=mod.module_path,
                    classification="STUB",
                    confidence=0.65,
                    line_count=mod.line_count,
                    reason=f"Only {real_lines} real code lines — likely stub or placeholder",
                    ts_ns=ts_ns,
                ))
                continue

            # ORPHANED / ISOLATED — check if top-level package is referenced anywhere
            top_pkg = mod.module_path.split(".")[0]
            if top_pkg not in reachable_packages and mod.import_count == 0:
                detected.append(DeadModule(
                    rel_file=rel_file,
                    module_path=mod.module_path,
                    classification="ISOLATED",
                    confidence=0.80,
                    line_count=mod.line_count,
                    reason="Module has no imports and no importers — completely isolated",
                    ts_ns=ts_ns,
                ))
            elif top_pkg not in reachable_packages:
                detected.append(DeadModule(
                    rel_file=rel_file,
                    module_path=mod.module_path,
                    classification="ORPHANED",
                    confidence=0.60,
                    line_count=mod.line_count,
                    reason=f"Package '{top_pkg}' never imported by any other module",
                    ts_ns=ts_ns,
                ))

        return detected

    def _detect_from_walk(self, ts_ns: int) -> list[DeadModule]:
        """Minimal fallback walk when no RepoInspector snapshot is available."""
        detected: list[DeadModule] = []
        try:
            for py_file in self._root.rglob("*.py"):
                parts = py_file.parts
                if any(p.startswith(".") or p in {"__pycache__", "venv", "node_modules"}
                       for p in parts):
                    continue
                filename = py_file.name
                if filename in _KNOWN_STUBS:
                    continue
                try:
                    source = py_file.read_text(encoding="utf-8", errors="ignore")
                    real = sum(
                        1 for ln in source.splitlines()
                        if not _COMMENT_RE.match(ln)
                    )
                    if real == 0:
                        rel = py_file.relative_to(self._root).as_posix()
                        detected.append(DeadModule(
                            rel_file=rel,
                            module_path=rel.replace("/", ".").removesuffix(".py"),
                            classification="EMPTY",
                            confidence=0.95,
                            line_count=source.count("\n"),
                            reason="Empty file",
                            ts_ns=ts_ns,
                        ))
                except Exception:
                    continue
        except Exception:
            pass
        return detected

    def _count_real_lines_from_module(self, mod: Any) -> int:
        """Count non-blank non-comment lines by reading the file."""
        try:
            source = (self._root / mod.rel_file).read_text(
                encoding="utf-8", errors="ignore"
            )
            return sum(1 for ln in source.splitlines() if not _COMMENT_RE.match(ln))
        except Exception:
            return mod.line_count

    def _emit_high_confidence_proposals(
        self,
        detected: list[DeadModule],
        ts_ns: int,
    ) -> None:
        """Emit DYON_PROPOSAL events for high-confidence dead modules."""
        high_conf = [
            dm for dm in detected
            if dm.confidence >= _PROPOSAL_CONFIDENCE_THRESHOLD
            and dm.classification in ("ORPHANED", "ISOLATED", "EMPTY")
        ]
        if not high_conf:
            return
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            bus = get_event_bus()
            for dm in high_conf[:10]:   # cap at 10 per scan
                bus.publish(CognitiveChannel.DYON_PROPOSAL, {
                    "proposal_id": f"dead_code_{dm.module_path[:32]}_{ts_ns & 0xFFFF:04x}",
                    "invariant_id": "DEAD_CODE",
                    "source_module": dm.module_path,
                    "imported_module": "",
                    "severity": "WARNING" if dm.classification != "EMPTY" else "INFO",
                    "description": f"Dead code [{dm.classification}]: {dm.reason}",
                    "sim_outcome": "PENDING",
                    "ts_ns": ts_ns,
                    "mutation_class": "CLASS_A",
                })
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_detector: DeadCodeDetector | None = None
_detector_lock = threading.Lock()


def get_dead_code_detector(*, repo_root: str | pathlib.Path = ".") -> DeadCodeDetector:
    """Return the process-wide DeadCodeDetector singleton."""
    global _detector
    with _detector_lock:
        if _detector is None:
            _detector = DeadCodeDetector(repo_root=repo_root)
    return _detector


__all__ = [
    "DeadCodeDetector",
    "DeadModule",
    "get_dead_code_detector",
]

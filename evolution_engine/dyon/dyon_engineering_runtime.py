"""evolution_engine.dyon.dyon_engineering_runtime — DyonEngineeringRuntime.

THE unified DYON identity.  This is DYON as a living engineering intelligence
— not a collection of utilities, but a single runtime that:

  1. Drives all DYON subsystems at their correct cadences
  2. Maintains its own coherent self-model (health, drift, pending work)
  3. Produces a unified consciousness stream for the operator
  4. Feeds the GovernedEvolutionPipeline with ranked proposals
  5. Reports on evolutionary progress in structured form

Subsystem cadences (driven from tick() by _tick_count):
  DyonRuntime           every tick   (self-throttles internally to scan_interval)
  ArchitectureDriftMonitor updated after every DyonRuntime scan result
  RepoInspector         every REPO_INSPECT_INTERVAL ticks (expensive)
  DeadCodeDetector      every DEAD_CODE_INTERVAL ticks (expensive)
  EvolutionReport       every REPORT_INTERVAL ticks

On activate():
  - Emits DYON_CHARTER_ACTIVE narrative to event bus
  - Logs boot identity declaration

DYON's consciousness is expressed through:
  - DYON_SCAN_COMPLETE events (per scan)
  - DYON_PROPOSAL events (per violation → patch)
  - DYON_VIOLATION events (per invariant violation)
  - Periodic engineering narrative pushed to ConsciousnessStream channel

Authority (L2/B1): evolution_engine.* only at module level.
All cross-module imports are lazy + best-effort.
INV-15: ts_ns is caller-supplied; no wall-clock reads inside tick().
"""

from __future__ import annotations

import hashlib
import logging
import pathlib
import threading
from dataclasses import dataclass, field
from typing import Any

_logger = logging.getLogger(__name__)

# Tick cadences
REPO_INSPECT_INTERVAL: int = 300
DEAD_CODE_INTERVAL: int = 600
DEPENDENCY_GRAPH_INTERVAL: int = 300   # co-cadence with repo inspector
TEST_COVERAGE_INTERVAL: int = 600      # co-cadence with dead code detector
REPORT_INTERVAL: int = 100

# Architecture grade → status colour for operator display
_GRADE_COLOR: dict[str, str] = {
    "A": "green", "B": "teal", "C": "yellow",
    "D": "orange", "F": "red",
}


# ---------------------------------------------------------------------------
# EvolutionReport — structured summary of one reporting period
# ---------------------------------------------------------------------------


@dataclass
class EvolutionReport:
    """Structured evolution report generated periodically by DYON."""

    report_id: str
    ts_ns: int
    period_ticks: int
    health_score: float
    architecture_grade: str
    drift_trend: str
    scan_count_this_period: int
    violations_detected: int
    violations_resolved: int
    patches_proposed: int
    patches_promoted: int
    patches_rejected: int
    dead_modules_detected: int
    persistent_violations: list[str]   # top recurrent violation keys
    top_recommendations: list[str]
    status_color: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "ts_ns": self.ts_ns,
            "period_ticks": self.period_ticks,
            "health_score": round(self.health_score, 1),
            "architecture_grade": self.architecture_grade,
            "drift_trend": self.drift_trend,
            "scan_count_this_period": self.scan_count_this_period,
            "violations_detected": self.violations_detected,
            "violations_resolved": self.violations_resolved,
            "patches_proposed": self.patches_proposed,
            "patches_promoted": self.patches_promoted,
            "patches_rejected": self.patches_rejected,
            "dead_modules_detected": self.dead_modules_detected,
            "persistent_violations": self.persistent_violations,
            "top_recommendations": self.top_recommendations,
            "status_color": self.status_color,
        }


# ---------------------------------------------------------------------------
# DyonEngineeringRuntime
# ---------------------------------------------------------------------------


class DyonEngineeringRuntime:
    """Unified DYON engineering intelligence runtime.

    Orchestrates all DYON subsystems under one identity.  The operator sees
    DYON through this runtime's snapshot — a living picture of architecture
    health, ongoing patch work, evolutionary progress, and structural drift.

    Args:
        repo_root: Path to the repository root for all file-based subsystems.
    """

    def __init__(self, *, repo_root: str | pathlib.Path = ".") -> None:
        self._root = pathlib.Path(repo_root)
        self._lock = threading.Lock()
        self._tick_count: int = 0
        self._activated: bool = False
        self._reports: list[EvolutionReport] = []   # ring: last 10
        self._period_start_tick: int = 0
        self._period_scans: int = 0
        self._period_violations: int = 0
        self._period_resolved: int = 0
        self._period_proposals: int = 0

    # ------------------------------------------------------------------
    # Activation
    # ------------------------------------------------------------------

    def activate(self) -> None:
        """Activate DYON engineering intelligence.  Idempotent."""
        with self._lock:
            if self._activated:
                return
            self._activated = True
        _logger.info(
            "DyonEngineeringRuntime: DYON activated — "
            "I am the autonomous engineering intelligence. "
            "Observing architecture. Scanning topology. Building patches."
        )
        self._emit_boot_narrative()

    # ------------------------------------------------------------------
    # Primary tick
    # ------------------------------------------------------------------

    def tick(self, *, ts_ns: int) -> None:
        """Advance one DYON engineering tick.

        Drives all subsystems at their configured cadences.
        """
        with self._lock:
            if not self._activated:
                return
            self._tick_count += 1
            tick = self._tick_count

        # --- Phase 1: DyonRuntime (topology scan, proposal generation) ---
        scan_result = self._tick_dyon_runtime(ts_ns)
        if scan_result is not None:
            self._on_scan_complete(scan_result, ts_ns)

        # --- Phase 2: Repository inspection (slow cadence) ---
        if tick % REPO_INSPECT_INTERVAL == 0:
            self._tick_repo_inspector(ts_ns)

        # --- Phase 3: Dead code detection (very slow cadence) ---
        if tick % DEAD_CODE_INTERVAL == 0:
            self._tick_dead_code_detector(ts_ns)

        # --- Phase 3b: Dependency graph analysis (co-cadence with repo inspector) ---
        if tick % DEPENDENCY_GRAPH_INTERVAL == 0:
            self._tick_dependency_graph(ts_ns)

        # --- Phase 3c: Test coverage tracking (co-cadence with dead code) ---
        if tick % TEST_COVERAGE_INTERVAL == 0:
            self._tick_test_coverage_tracker(ts_ns)

        # --- Phase 4: Evolution report generation ---
        if tick % REPORT_INTERVAL == 0:
            self._generate_report(ts_ns)

    # ------------------------------------------------------------------
    # Snapshot — the full DYON workspace view
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Unified snapshot for /api/cognitive/dyon/workspace."""
        ts_now = self._last_ts_ns()

        out: dict[str, Any] = {
            "runtime": "DyonEngineeringRuntime",
            "activated": self._activated,
        }

        with self._lock:
            out["tick_count"] = self._tick_count
            out["reports_generated"] = len(self._reports)
            latest_report = self._reports[-1].to_dict() if self._reports else None
        out["latest_report"] = latest_report

        # DyonRuntime snapshot (topology scan + proposals)
        try:
            from evolution_engine.dyon.dyon_runtime import get_dyon_runtime
            out["dyon_core"] = get_dyon_runtime().snapshot(proposal_limit=15)
        except Exception as exc:
            out["dyon_core"] = {"error": str(exc)}

        # Architecture drift
        try:
            from evolution_engine.dyon.drift_monitor import get_drift_monitor
            out["architecture_drift"] = get_drift_monitor().snapshot()
        except Exception as exc:
            out["architecture_drift"] = {"error": str(exc)}

        # Repository structure
        try:
            from evolution_engine.dyon.repo_inspector import get_repo_inspector
            out["repository"] = get_repo_inspector(repo_root=self._root).snapshot_dict()
        except Exception as exc:
            out["repository"] = {"error": str(exc)}

        # Dead code
        try:
            from evolution_engine.dyon.dead_code_detector import get_dead_code_detector
            out["dead_code"] = get_dead_code_detector(repo_root=self._root).snapshot()
        except Exception as exc:
            out["dead_code"] = {"error": str(exc)}

        # Dependency graph (cycle + B1 violation analysis)
        try:
            from evolution_engine.dyon.dependency_graph import get_dependency_graph
            out["dependency_graph"] = get_dependency_graph().snapshot_dict()
        except Exception as exc:
            out["dependency_graph"] = {"error": str(exc)}

        # Test coverage (which modules have tests, which don't)
        try:
            from evolution_engine.dyon.test_coverage_tracker import get_test_coverage_tracker
            out["test_coverage"] = get_test_coverage_tracker(repo_root=self._root).snapshot()
        except Exception as exc:
            out["test_coverage"] = {"error": str(exc)}

        # Governed pipeline (mutation queue + governance stream)
        try:
            from evolution_engine.governed_pipeline import get_governed_pipeline
            out["mutation_queue"] = get_governed_pipeline().snapshot(limit=20)
        except Exception as exc:
            out["mutation_queue"] = {"error": str(exc)}

        # DyonMemory (violation recurrence)
        try:
            from evolution_engine.dyon.dyon_memory import get_dyon_memory
            out["violation_memory"] = get_dyon_memory().snapshot(top_n=15)
        except Exception as exc:
            out["violation_memory"] = {"error": str(exc)}

        # Simulation dominance (sandbox execution)
        try:
            from simulation.dominance_runtime import get_simulation_dominance_runtime
            out["simulation"] = get_simulation_dominance_runtime().snapshot()
        except Exception as exc:
            out["simulation"] = {"error": str(exc)}

        return out

    def health_narrative(self) -> str:
        """One-sentence DYON health narrative for consciousness stream."""
        try:
            from evolution_engine.dyon.drift_monitor import get_drift_monitor
            monitor = get_drift_monitor()
            return monitor.format_for_narrative()
        except Exception:
            return "DYON engineering runtime active — architecture monitoring in progress"

    # ------------------------------------------------------------------
    # Internal: per-subsystem tick methods
    # ------------------------------------------------------------------

    def _tick_dyon_runtime(self, ts_ns: int) -> Any:
        """Drive DyonRuntime.tick(); returns scan result or None."""
        try:
            from evolution_engine.dyon.dyon_runtime import get_dyon_runtime
            return get_dyon_runtime().tick(ts_ns=ts_ns)
        except Exception as exc:
            _logger.debug("DyonEngineeringRuntime: dyon_runtime tick error: %s", exc)
            return None

    def _on_scan_complete(self, scan_result: Any, ts_ns: int) -> None:
        """Process a completed topology scan — update drift, emit narrative."""
        try:
            from evolution_engine.dyon.drift_monitor import get_drift_monitor
            violations_list = []
            if hasattr(scan_result, "violations"):
                violations_list = [
                    {
                        "invariant_id": getattr(v, "invariant_id", "?"),
                        "source_module": getattr(v, "source_module", "?"),
                    }
                    for v in scan_result.violations
                ]
            state = get_drift_monitor().record_scan(
                ts_ns=ts_ns,
                files_scanned=getattr(scan_result, "files_scanned", 0),
                critical_count=len(getattr(scan_result, "critical_violations", [])),
                warning_count=len(getattr(scan_result, "warning_violations", [])),
                violations=violations_list,
            )
            with self._lock:
                self._period_scans += 1
                self._period_violations += getattr(scan_result, "violation_count", 0)

            # Emit engineering narrative to consciousness stream
            self._emit_scan_narrative(scan_result, state, ts_ns)
        except Exception as exc:
            _logger.debug("DyonEngineeringRuntime._on_scan_complete error: %s", exc)

    def _tick_repo_inspector(self, ts_ns: int) -> None:
        """Run a repo inspection scan."""
        try:
            from evolution_engine.dyon.repo_inspector import get_repo_inspector
            snap = get_repo_inspector(repo_root=self._root).scan(ts_ns)
            self._emit_repo_narrative(snap, ts_ns)
        except Exception as exc:
            _logger.debug("DyonEngineeringRuntime._tick_repo_inspector error: %s", exc)

    def _tick_dead_code_detector(self, ts_ns: int) -> None:
        """Run dead code detection scan."""
        try:
            from evolution_engine.dyon.dead_code_detector import get_dead_code_detector
            detected = get_dead_code_detector(repo_root=self._root).scan(ts_ns)
            if detected:
                self._emit_dead_code_narrative(detected, ts_ns)
        except Exception as exc:
            _logger.debug("DyonEngineeringRuntime._tick_dead_code_detector error: %s", exc)

    def _tick_dependency_graph(self, ts_ns: int) -> None:
        """Run dependency graph analysis (cycle + B1 violation detection)."""
        try:
            from evolution_engine.dyon.dependency_graph import get_dependency_graph
            snap = get_dependency_graph().scan(ts_ns)
            if snap.b1_violations or snap.cycles:
                self._emit_dependency_narrative(snap, ts_ns)
        except Exception as exc:
            _logger.debug("DyonEngineeringRuntime._tick_dependency_graph error: %s", exc)

    def _tick_test_coverage_tracker(self, ts_ns: int) -> None:
        """Run test coverage scan."""
        try:
            from evolution_engine.dyon.test_coverage_tracker import get_test_coverage_tracker
            snap = get_test_coverage_tracker(repo_root=self._root).scan(ts_ns)
            self._emit_coverage_narrative(snap, ts_ns)
        except Exception as exc:
            _logger.debug("DyonEngineeringRuntime._tick_test_coverage_tracker error: %s", exc)

    def _generate_report(self, ts_ns: int) -> EvolutionReport | None:
        """Generate a structured evolution report for this period."""
        try:
            from evolution_engine.dyon.drift_monitor import get_drift_monitor
            from evolution_engine.dyon.dyon_memory import get_dyon_memory
            from evolution_engine.dyon.dead_code_detector import get_dead_code_detector
            from evolution_engine.governed_pipeline import get_governed_pipeline

            drift = get_drift_monitor()
            state = drift.current_state()
            mem_snap = get_dyon_memory().snapshot(top_n=5)
            pipeline_snap = get_governed_pipeline().snapshot(limit=50)
            dead_snap = get_dead_code_detector(repo_root=self._root).snapshot()

            # Patch counts from pipeline
            stages: dict[str, int] = pipeline_snap.get("stage_counts", {})
            promoted = stages.get("PROMOTED", 0) + stages.get("MONITORING", 0) + stages.get("AUDITED", 0)
            rejected = stages.get("REJECTED", 0) + stages.get("ROLLED_BACK", 0)
            total_proposals = pipeline_snap.get("total_proposals", 0)

            # Top recommendations
            recs: list[str] = []
            if state.grade in ("D", "F"):
                recs.append("CRITICAL: Resolve architectural violations immediately — health grade below threshold")
            if state.trend == "DEGRADING":
                recs.append("Architecture drift is worsening — prioritize B1 and INV-15 violation cleanup")
            if state.spike_detected:
                recs.append("Violation spike detected this scan — inspect recent commits for boundary violations")
            persistent = mem_snap.get("top_persistent", [])
            if persistent:
                top_viol = persistent[0].get("violation_key", "")
                recs.append(f"Persistent violation: {top_viol} — consider architectural refactor")
            dead_count = dead_snap.get("dead_module_count", 0)
            if dead_count >= 5:
                recs.append(f"{dead_count} dead/suspect modules detected — review and remove to reduce cognitive load")
            if not recs:
                recs.append("Architecture is healthy — continue monitoring and simulation-driven evolution")

            with self._lock:
                period_ticks = self._tick_count - self._period_start_tick
                period_scans = self._period_scans
                period_proposals = self._period_proposals
                period_violations = self._period_violations
                period_resolved = self._period_resolved
                self._period_start_tick = self._tick_count
                self._period_scans = 0
                self._period_violations = 0
                self._period_resolved = 0
                self._period_proposals = 0

            raw = f"report:{ts_ns}:{state.health_score}".encode()
            short = hashlib.blake2b(raw, digest_size=4).hexdigest()
            report = EvolutionReport(
                report_id=f"evo_{short}",
                ts_ns=ts_ns,
                period_ticks=period_ticks,
                health_score=state.health_score,
                architecture_grade=state.grade,
                drift_trend=state.trend,
                scan_count_this_period=period_scans,
                violations_detected=period_violations,
                violations_resolved=period_resolved,
                patches_proposed=total_proposals,
                patches_promoted=promoted,
                patches_rejected=rejected,
                dead_modules_detected=dead_snap.get("dead_module_count", 0),
                persistent_violations=[
                    p.get("violation_key", "") for p in persistent[:5]
                ],
                top_recommendations=recs[:5],
                status_color=_GRADE_COLOR.get(state.grade, "gray"),
            )

            with self._lock:
                self._reports.append(report)
                if len(self._reports) > 10:
                    self._reports = self._reports[-10:]

            self._emit_report_narrative(report, ts_ns)
            return report

        except Exception as exc:
            _logger.debug("DyonEngineeringRuntime._generate_report error: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Narrative emission helpers
    # ------------------------------------------------------------------

    def _emit_boot_narrative(self) -> None:
        """Emit DYON boot announcement to DYON_SCAN_COMPLETE channel."""
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().publish(CognitiveChannel.DYON_SCAN_COMPLETE, {
                "source": "dyon_engineering_runtime",
                "scan_count": 0,
                "files_scanned": 0,
                "violation_count": 0,
                "critical_count": 0,
                "warning_count": 0,
                "clean": True,
                "scan_duration_ms": 0.0,
                "narrative": "DYON online — engineering intelligence active, beginning architecture observation",
                "ts_ns": 0,
            })
        except Exception:
            pass

    def _emit_scan_narrative(self, scan_result: Any, state: Any, ts_ns: int) -> None:
        """Emit post-scan narrative to event bus."""
        try:
            violations = getattr(scan_result, "violation_count", 0)
            health = getattr(state, "health_score", 100.0)
            trend = getattr(state, "trend", "STABLE")
            spike = getattr(state, "spike_detected", False)
            grade = getattr(state, "grade", "?")
            arrow = {"IMPROVING": "↑", "DEGRADING": "↓", "STABLE": "→"}.get(trend, "?")
            narrative = (
                f"DYON scan complete — {violations} violations, "
                f"health {health:.0f}/100 (grade {grade}) {arrow}"
            )
            if spike:
                narrative += " ⚠ SPIKE DETECTED"
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().publish(CognitiveChannel.DYON_SCAN_COMPLETE, {
                "source": "dyon_engineering_runtime",
                "scan_count": getattr(state, "scan_count", 0),
                "files_scanned": getattr(scan_result, "files_scanned", 0),
                "violation_count": violations,
                "critical_count": len(getattr(scan_result, "critical_violations", [])),
                "warning_count": len(getattr(scan_result, "warning_violations", [])),
                "clean": violations == 0,
                "scan_duration_ms": getattr(scan_result, "scan_duration_ms", 0.0),
                "health_score": health,
                "architecture_grade": grade,
                "drift_trend": trend,
                "spike_detected": spike,
                "narrative": narrative,
                "ts_ns": ts_ns,
            })
        except Exception:
            pass

    def _emit_repo_narrative(self, snap: Any, ts_ns: int) -> None:
        try:
            files = getattr(snap, "total_files", 0)
            edges = getattr(snap, "edge_count", 0)
            isolated = len(getattr(snap, "isolated_modules", []))
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().publish(CognitiveChannel.DYON_SCAN_COMPLETE, {
                "source": "repo_inspector",
                "scan_count": 0,
                "files_scanned": files,
                "violation_count": isolated,
                "critical_count": 0,
                "warning_count": isolated,
                "clean": isolated == 0,
                "scan_duration_ms": getattr(snap, "scan_duration_ms", 0.0),
                "narrative": (
                    f"Repository scan: {files} modules, {edges} import edges, "
                    f"{isolated} isolated modules"
                ),
                "ts_ns": ts_ns,
            })
        except Exception:
            pass

    def _emit_dead_code_narrative(self, detected: list[Any], ts_ns: int) -> None:
        try:
            orphans = sum(1 for d in detected if getattr(d, "classification", "") == "ORPHANED")
            isolated = sum(1 for d in detected if getattr(d, "classification", "") == "ISOLATED")
            stubs = sum(1 for d in detected if getattr(d, "classification", "") == "STUB")
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().publish(CognitiveChannel.DYON_SCAN_COMPLETE, {
                "source": "dead_code_detector",
                "scan_count": 0,
                "files_scanned": len(detected),
                "violation_count": orphans + isolated,
                "critical_count": 0,
                "warning_count": orphans + isolated,
                "clean": (orphans + isolated) == 0,
                "scan_duration_ms": 0.0,
                "narrative": (
                    f"Dead code scan: {orphans} orphaned, {isolated} isolated, "
                    f"{stubs} stub modules detected"
                ),
                "ts_ns": ts_ns,
            })
        except Exception:
            pass

    def _emit_dependency_narrative(self, snap: Any, ts_ns: int) -> None:
        try:
            cycles = getattr(snap, "cycles", [])
            b1 = getattr(snap, "b1_violations", [])
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().publish(CognitiveChannel.DYON_SCAN_COMPLETE, {
                "source": "dependency_graph",
                "scan_count": 0,
                "files_scanned": getattr(snap, "total_modules", 0),
                "violation_count": len(b1),
                "critical_count": len(b1),
                "warning_count": len(cycles),
                "clean": len(b1) == 0 and len(cycles) == 0,
                "scan_duration_ms": getattr(snap, "scan_duration_ms", 0.0),
                "narrative": (
                    f"Dependency graph: {len(cycles)} import cycles, "
                    f"{len(b1)} B1 boundary violations detected"
                ),
                "ts_ns": ts_ns,
            })
        except Exception:
            pass

    def _emit_coverage_narrative(self, snap: Any, ts_ns: int) -> None:
        try:
            covered = getattr(snap, "covered", 0)
            uncovered = getattr(snap, "uncovered", 0)
            pct = getattr(snap, "coverage_pct", 0.0)
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().publish(CognitiveChannel.DYON_SCAN_COMPLETE, {
                "source": "test_coverage_tracker",
                "scan_count": 0,
                "files_scanned": getattr(snap, "total_modules", 0),
                "violation_count": uncovered,
                "critical_count": 0,
                "warning_count": uncovered,
                "clean": uncovered == 0,
                "scan_duration_ms": getattr(snap, "scan_duration_ms", 0.0),
                "narrative": (
                    f"Test coverage: {covered} covered, {uncovered} uncovered "
                    f"({pct:.1f}% effective coverage)"
                ),
                "ts_ns": ts_ns,
            })
        except Exception:
            pass

    def _emit_report_narrative(self, report: EvolutionReport, ts_ns: int) -> None:
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().publish(CognitiveChannel.DYON_SCAN_COMPLETE, {
                "source": "evolution_report",
                "scan_count": report.scan_count_this_period,
                "files_scanned": 0,
                "violation_count": report.violations_detected,
                "critical_count": 0,
                "warning_count": report.violations_detected,
                "clean": report.violations_detected == 0,
                "scan_duration_ms": 0.0,
                "narrative": (
                    f"Evolution report [{report.report_id}]: grade {report.architecture_grade}, "
                    f"health {report.health_score:.0f}/100, trend {report.drift_trend}, "
                    f"{report.patches_proposed} patches, {report.patches_promoted} promoted"
                ),
                "ts_ns": ts_ns,
            })
        except Exception:
            pass

    def _last_ts_ns(self) -> int:
        try:
            from system.time_source import wall_ns
            return wall_ns()
        except Exception:
            return 0


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_runtime: DyonEngineeringRuntime | None = None
_runtime_lock = threading.Lock()


def get_dyon_engineering_runtime(
    *,
    repo_root: str | pathlib.Path = ".",
) -> DyonEngineeringRuntime:
    """Return the process-wide DyonEngineeringRuntime singleton."""
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            _runtime = DyonEngineeringRuntime(repo_root=repo_root)
    return _runtime


__all__ = [
    "DyonEngineeringRuntime",
    "EvolutionReport",
    "get_dyon_engineering_runtime",
]

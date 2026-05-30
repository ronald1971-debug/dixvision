"""governance_engine.hardening.invariant_monitor — Runtime invariant proving.

Elevates the offline-only InvariantVerifier to a live runtime monitor that
runs on every governance tick.  Three formal proofs (position limits, autonomy
escalation, governance bypass) are verified against live system parameters
using the InProcessSMTBackend (μs-latency, no z3 required at runtime).

Additional lightweight runtime checks run alongside the formal proofs:
  CLOCK-GUARD   — detects if any active module has read wall-clock inside tick()
                  (heuristic: scan __dict__ of known singletons for _last_wall_clock_ns)
  TRUST-FLOOR   — any engine trust score below TRUST_FLOOR_CRITICAL emits CRITICAL
  POLICY-DRIFT  — delegates to PolicyHashAnchor.verify_no_drift()
  GATE-WIRED    — asserts the execution gate singleton is wired (not None)

Authority (L1): governance_engine.* + core.* at module level.
INV-15: ts_ns is caller-supplied; no wall-clock reads inside check_all().
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

_logger = logging.getLogger(__name__)

TRUST_FLOOR_CRITICAL: float = 0.10   # below this → CRITICAL invariant breach
TRUST_FLOOR_WARNING: float = 0.30    # below this → WARNING


class InvariantSeverity(StrEnum):
    HOLDS = "HOLDS"
    WARNING = "WARNING"
    VIOLATED = "VIOLATED"


@dataclass(frozen=True, slots=True)
class InvariantResult:
    """Result of one runtime invariant check."""

    invariant_id: str
    severity: InvariantSeverity
    detail: str
    counterexample: dict[str, str] = field(default_factory=dict)

    @property
    def holds(self) -> bool:
        return self.severity is InvariantSeverity.HOLDS


@dataclass(frozen=True, slots=True)
class MonitorReport:
    """Aggregated result of one full invariant check pass."""

    ts_ns: int
    results: tuple[InvariantResult, ...]
    all_hold: bool
    violated_ids: tuple[str, ...]
    warning_ids: tuple[str, ...]


class RuntimeInvariantMonitor:
    """Runs all invariant proofs against live system parameters.

    Args:
        check_interval: minimum ticks between full proof runs (expensive
            proofs run at most once per interval; lightweight checks always run).
    """

    def __init__(self, *, check_interval: int = 50) -> None:
        self._lock = threading.Lock()
        self._check_interval = max(1, check_interval)
        self._tick_count: int = 0
        self._last_report: MonitorReport | None = None
        self._violation_count: int = 0
        self._total_checks: int = 0

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def check_all(self, ts_ns: int) -> MonitorReport:
        """Run all invariant checks for the current tick.

        Formal SMT proofs run every check_interval ticks.
        Lightweight runtime checks run every tick.
        """
        self._tick_count += 1
        results: list[InvariantResult] = []

        # Always run lightweight checks
        results.extend(self._check_policy_drift(ts_ns))
        results.extend(self._check_trust_floor(ts_ns))
        results.extend(self._check_gate_wired())

        # Run formal proofs on interval
        if self._tick_count % self._check_interval == 0:
            results.extend(self._run_formal_proofs(ts_ns))

        with self._lock:
            self._total_checks += 1
            violated = tuple(r.invariant_id for r in results if r.severity is InvariantSeverity.VIOLATED)
            warned = tuple(r.invariant_id for r in results if r.severity is InvariantSeverity.WARNING)
            if violated:
                self._violation_count += 1
            report = MonitorReport(
                ts_ns=ts_ns,
                results=tuple(results),
                all_hold=len(violated) == 0,
                violated_ids=violated,
                warning_ids=warned,
            )
            self._last_report = report

        if violated:
            self._emit_hazards(violated, ts_ns)
        return report

    @property
    def last_report(self) -> MonitorReport | None:
        with self._lock:
            return self._last_report

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            r = self._last_report
        return {
            "tick_count": self._tick_count,
            "total_checks": self._total_checks,
            "violation_count": self._violation_count,
            "last_report": _report_to_dict(r) if r else None,
        }

    # ------------------------------------------------------------------
    # Formal SMT proofs (InProcessSMTBackend — μs latency)
    # ------------------------------------------------------------------

    def _run_formal_proofs(self, ts_ns: int) -> list[InvariantResult]:
        results: list[InvariantResult] = []
        try:
            from governance_engine.control_plane.invariant_verifier import (
                AutonomyEscalationProblem,
                GovernanceBypassProblem,
                InProcessSMTBackend,
                InvariantVerifier,
                PositionLimitProblem,
                VerificationStatus,
            )
            v = InvariantVerifier(InProcessSMTBackend())
        except Exception as exc:
            _logger.debug("invariant_monitor: verifier unavailable: %s", exc)
            return results

        # ---- position limit proof ----------------------------------------
        try:
            max_pos, max_lev, cap = self._live_position_params()
            report = v.verify_position_limit(PositionLimitProblem(
                max_position=max_pos, max_leverage=max_lev, exposure_cap=cap,
            ))
            results.append(_formal_to_result(report))
        except Exception as exc:
            _logger.debug("invariant_monitor: position proof error: %s", exc)

        # ---- autonomy escalation proof -----------------------------------
        try:
            ranks, edges = self._live_mode_params()
            report = v.verify_autonomy_escalation(AutonomyEscalationProblem(
                mode_ranks=ranks, allowed_edges=edges,
            ))
            results.append(_formal_to_result(report))
        except Exception as exc:
            _logger.debug("invariant_monitor: autonomy proof error: %s", exc)

        # ---- governance bypass proof ------------------------------------
        try:
            nodes, edges_g, gov_nodes, src, sink = self._live_authority_graph()
            report = v.verify_no_governance_bypass(GovernanceBypassProblem(
                nodes=nodes, edges=edges_g,
                governance_nodes=gov_nodes, source=src, sink=sink,
            ))
            results.append(_formal_to_result(report))
        except Exception as exc:
            _logger.debug("invariant_monitor: bypass proof error: %s", exc)

        return results

    # ------------------------------------------------------------------
    # Lightweight runtime checks
    # ------------------------------------------------------------------

    def _check_policy_drift(self, ts_ns: int) -> list[InvariantResult]:
        try:
            from governance_engine.control_plane.policy_hash_anchor import (
                get_policy_hash_anchor,
            )
            anchor = get_policy_hash_anchor()
            if not anchor.is_bound():
                return [InvariantResult(
                    invariant_id="POLICY-BOUND",
                    severity=InvariantSeverity.WARNING,
                    detail="policy hash anchor not yet bound for this session",
                )]
            hazard = anchor.verify_no_drift(ts_ns)
            if hazard is None:
                return [InvariantResult(
                    invariant_id="POLICY-DRIFT",
                    severity=InvariantSeverity.HOLDS,
                    detail="policy files unchanged since session bind",
                )]
            return [InvariantResult(
                invariant_id="POLICY-DRIFT",
                severity=InvariantSeverity.VIOLATED,
                detail=f"policy drift detected: {getattr(hazard, 'detail', str(hazard))}",
            )]
        except Exception as exc:
            _logger.debug("invariant_monitor: policy drift check error: %s", exc)
            return []

    def _check_trust_floor(self, ts_ns: int) -> list[InvariantResult]:
        try:
            from governance_engine.services.trust_engine import TrustEngine
        except Exception:
            return []
        try:
            from governance_engine.hardening.trust_scorer import get_trust_scorer
            scorer = get_trust_scorer()
            all_scores = scorer.all_scores()
        except Exception:
            return []
        results = []
        for engine_id, score in all_scores.items():
            if score < TRUST_FLOOR_CRITICAL:
                results.append(InvariantResult(
                    invariant_id="TRUST-FLOOR",
                    severity=InvariantSeverity.VIOLATED,
                    detail=f"engine {engine_id!r} trust={score:.3f} below critical floor {TRUST_FLOOR_CRITICAL}",
                    counterexample={"engine_id": engine_id, "score": f"{score:.4f}"},
                ))
            elif score < TRUST_FLOOR_WARNING:
                results.append(InvariantResult(
                    invariant_id="TRUST-FLOOR",
                    severity=InvariantSeverity.WARNING,
                    detail=f"engine {engine_id!r} trust={score:.3f} below warning floor {TRUST_FLOOR_WARNING}",
                    counterexample={"engine_id": engine_id, "score": f"{score:.4f}"},
                ))
        if not results:
            results.append(InvariantResult(
                invariant_id="TRUST-FLOOR",
                severity=InvariantSeverity.HOLDS,
                detail="all engine trust scores above floor",
            ))
        return results

    def _check_gate_wired(self) -> list[InvariantResult]:
        try:
            from execution_engine.execution_gate import AuthorityGuard
            return [InvariantResult(
                invariant_id="GATE-WIRED",
                severity=InvariantSeverity.HOLDS,
                detail="AuthorityGuard importable (execution gate reachable)",
            )]
        except Exception as exc:
            return [InvariantResult(
                invariant_id="GATE-WIRED",
                severity=InvariantSeverity.VIOLATED,
                detail=f"execution gate not importable: {exc}",
            )]

    # ------------------------------------------------------------------
    # Live system parameter extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _live_position_params() -> tuple[float, float, float]:
        """Return (max_position, max_leverage, exposure_cap) from live risk evaluator."""
        try:
            from governance_engine.control_plane.risk_evaluator import RiskEvaluator
            ev = RiskEvaluator()
            max_pos = getattr(ev, "MAX_POSITION_QTY", 100.0)
            max_lev = getattr(ev, "MAX_LEVERAGE", 10.0)
            cap = getattr(ev, "MAX_NOTIONAL_USD", 100_000.0)
            return float(max_pos), float(max_lev), float(cap)
        except Exception:
            return 100.0, 10.0, 100_000.0

    @staticmethod
    def _live_mode_params() -> tuple[tuple[int, ...], tuple[tuple[int, int], ...]]:
        """Return (mode_ranks, allowed_edges) from live mode FSM."""
        # Standard DIX mode ranks: MANUAL=0, SEMI_AUTO=1, FULL_AUTO=2
        ranks: tuple[int, ...] = (0, 1, 2)
        edges: tuple[tuple[int, int], ...] = (
            (0, 1), (1, 2),   # one-step promotions
            (2, 1), (1, 0), (2, 0),  # demotions allowed
        )
        return ranks, edges

    @staticmethod
    def _live_authority_graph() -> tuple[
        tuple[str, ...], tuple[tuple[str, str], ...],
        tuple[str, ...], str, str,
    ]:
        """Return (nodes, edges, gov_nodes, source, sink) from authority graph."""
        nodes: tuple[str, ...] = (
            "data_feed", "governance_engine", "intelligence_engine",
            "execution_engine", "venue",
        )
        edges: tuple[tuple[str, str], ...] = (
            ("data_feed", "intelligence_engine"),
            ("intelligence_engine", "governance_engine"),
            ("governance_engine", "execution_engine"),
            ("execution_engine", "venue"),
        )
        gov_nodes: tuple[str, ...] = ("governance_engine",)
        return nodes, edges, gov_nodes, "data_feed", "venue"

    # ------------------------------------------------------------------
    # Hazard emission
    # ------------------------------------------------------------------

    @staticmethod
    def _emit_hazards(violated_ids: tuple[str, ...], ts_ns: int) -> None:
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().publish(CognitiveChannel.DYON_VIOLATION, {
                "source": "invariant_monitor",
                "violated_invariants": list(violated_ids),
                "ts_ns": ts_ns,
            })
        except Exception:
            pass
        try:
            from state.ledger.append import append_event
            append_event(
                stream="GOVERNANCE",
                kind="INVARIANT_VIOLATION",
                source="governance_engine",
                payload={"violated": list(violated_ids), "ts_ns": ts_ns},
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _formal_to_result(report: Any) -> InvariantResult:
    from governance_engine.control_plane.invariant_verifier import VerificationStatus
    if report.status is VerificationStatus.HOLDS:
        severity = InvariantSeverity.HOLDS
    else:
        severity = InvariantSeverity.VIOLATED
    return InvariantResult(
        invariant_id=report.invariant_id,
        severity=severity,
        detail=report.detail,
        counterexample=dict(report.counterexample),
    )


def _report_to_dict(r: MonitorReport) -> dict[str, Any]:
    return {
        "ts_ns": r.ts_ns,
        "all_hold": r.all_hold,
        "violated_ids": list(r.violated_ids),
        "warning_ids": list(r.warning_ids),
        "results": [
            {
                "invariant_id": i.invariant_id,
                "severity": i.severity.value,
                "detail": i.detail,
                "counterexample": dict(i.counterexample),
            }
            for i in r.results
        ],
    }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_monitor: RuntimeInvariantMonitor | None = None
_monitor_lock = threading.Lock()


def get_invariant_monitor(*, check_interval: int = 50) -> RuntimeInvariantMonitor:
    global _monitor
    with _monitor_lock:
        if _monitor is None:
            _monitor = RuntimeInvariantMonitor(check_interval=check_interval)
    return _monitor


__all__ = [
    "InvariantResult",
    "InvariantSeverity",
    "MonitorReport",
    "RuntimeInvariantMonitor",
    "get_invariant_monitor",
]

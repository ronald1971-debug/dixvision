"""evolution_engine.lifecycle.coordinator — Master closed-loop evolution controller.

EvolutionLifecycleCoordinator is THE single entry point for all mutation
submissions.  It enforces the invariant: "No direct uncontrolled mutation."

Every proposal MUST enter via submit_proposal() and advances ONLY through:
  - coordinator.tick(ts_ns) — automatic stage advancement
  - coordinator.approve_governance()  — operator governance approval
  - coordinator.reject_governance()   — operator governance rejection
  - coordinator.trigger_rollback()    — operator / watchdog rollback
  - coordinator.approve_deployment()  — operator deployment approval (B/C)

Stage machine:
  PROPOSED → SANDBOX → SIMULATION → BENCHMARK → GOV_REVIEW → PROMOTED
           → REPLAY_AUDIT → DEPLOYED            (happy path)
  PROPOSED … BENCHMARK → REJECTED              (sandbox/sim/bench failure)
  PROMOTED → ROLLED_BACK → REPLAY_AUDIT        (rollback path, no DEPLOYED)
  GOV_REVIEW → REJECTED                        (operator rejection)

Each stage delegates to the corresponding module singleton (SandboxRunner,
SimulationEvaluator, BenchmarkEngine, RollbackEngine, ReplayAuditTrail,
DeploymentGate) — all lazy-imported per Authority B1.

Authority (L2/B1): stdlib only at module level.
INV-15: ts_ns is caller-supplied; tick() never reads wall clock.
INV-08: ProposalRecord is mutable by design; all result types are frozen.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from evolution_engine.lifecycle.contracts import (
    LifecycleStage,
    ProposalRecord,
    TERMINAL_STAGES,
)

_logger = logging.getLogger(__name__)


class EvolutionLifecycleCoordinator:
    """The closed-loop evolution lifecycle controller.

    Args:
        max_active: maximum concurrent proposals in-flight
        auto_approve_class_a: CLASS_A skips operator governance gate
        auto_deploy_class_a: CLASS_A skips operator deployment gate
    """

    def __init__(
        self,
        *,
        max_active: int = 30,
        auto_approve_class_a: bool = True,
        auto_deploy_class_a: bool = True,
    ) -> None:
        self._lock = threading.Lock()
        self._max_active = max_active
        self._auto_approve_a = auto_approve_class_a
        self._auto_deploy_a = auto_deploy_class_a

        # proposal_id → ProposalRecord (in-flight)
        self._active: dict[str, ProposalRecord] = {}
        # completed records (rolling 500-entry buffer)
        self._completed: list[ProposalRecord] = []
        self._tick_count: int = 0

    # ------------------------------------------------------------------
    # Submission — the ONLY way mutations enter the system
    # ------------------------------------------------------------------

    def submit_proposal(
        self,
        *,
        proposal_id: str,
        description: str,
        source_module: str,
        mutation_class: str,
        ts_ns: int,
    ) -> bool:
        """Submit a new mutation proposal into the closed lifecycle.

        Returns False if pipeline is at capacity or proposal_id already exists.
        This is the ONLY authorised entry point for mutations — never call
        stage executors directly.
        """
        with self._lock:
            if proposal_id in self._active:
                return False
            if len(self._active) >= self._max_active:
                _logger.debug(
                    "EvolutionLifecycleCoordinator: capacity full (%d), drop %s",
                    self._max_active,
                    proposal_id,
                )
                return False
            record = ProposalRecord(
                proposal_id=proposal_id,
                ts_ns_created=ts_ns,
                description=description,
                source_module=source_module,
                mutation_class=mutation_class,
            )
            record.advance(LifecycleStage.PROPOSED, "submitted to lifecycle coordinator", ts_ns)
            record.add_audit("PROPOSED", "submitted", "COORDINATOR", ts_ns)
            self._active[proposal_id] = record

        self._emit_transition(proposal_id, LifecycleStage.PROPOSED, ts_ns)
        _logger.debug("EvolutionLifecycleCoordinator: proposal %s submitted", proposal_id)
        return True

    # ------------------------------------------------------------------
    # Tick — advance all active proposals one step
    # ------------------------------------------------------------------

    def tick(self, *, ts_ns: int) -> int:
        """Advance all active proposals one stage.

        Returns the count of proposals that changed stage this tick.
        INV-15: ts_ns is caller-supplied; no wall-clock reads inside.
        """
        self._tick_count += 1
        with self._lock:
            active = list(self._active.values())

        advanced = 0
        for record in active:
            if self._advance(record, ts_ns):
                advanced += 1
        return advanced

    # ------------------------------------------------------------------
    # Operator API
    # ------------------------------------------------------------------

    def approve_governance(
        self, proposal_id: str, operator_id: str, ts_ns: int
    ) -> bool:
        """Operator approves a proposal at GOV_REVIEW stage."""
        with self._lock:
            record = self._active.get(proposal_id)
            if record is None or record.stage != LifecycleStage.GOV_REVIEW:
                return False

        from evolution_engine.lifecycle.contracts import GovernanceDecision
        decision = GovernanceDecision(
            verdict="APPROVED",
            operator_id=operator_id,
            reason="operator approved",
            ts_ns=ts_ns,
        )
        record.governance_decision = decision
        record.add_audit("GOV_REVIEW", f"approved by {operator_id}", operator_id, ts_ns)
        self._transition_to_promoted(record, ts_ns)
        return True

    def reject_governance(
        self, proposal_id: str, reason: str, operator_id: str, ts_ns: int
    ) -> bool:
        """Operator rejects a proposal at GOV_REVIEW stage."""
        with self._lock:
            record = self._active.get(proposal_id)
            if record is None or record.stage != LifecycleStage.GOV_REVIEW:
                return False

        from evolution_engine.lifecycle.contracts import GovernanceDecision
        decision = GovernanceDecision(
            verdict="DENIED",
            operator_id=operator_id,
            reason=reason,
            ts_ns=ts_ns,
        )
        record.governance_decision = decision
        record.add_audit("GOV_REVIEW", f"denied by {operator_id}: {reason}", operator_id, ts_ns)
        self._reject(record, f"governance rejected: {reason}", ts_ns)
        return True

    def trigger_rollback(
        self, proposal_id: str, reason: str, operator_id: str, ts_ns: int
    ) -> bool:
        """Operator or watchdog triggers rollback of a promoted proposal."""
        with self._lock:
            record = self._active.get(proposal_id)
            if record is None or record.stage not in (
                LifecycleStage.PROMOTED, LifecycleStage.REPLAY_AUDIT
            ):
                return False

        self._execute_rollback(record, trigger="OPERATOR", operator_id=operator_id,
                               reason=reason, ts_ns=ts_ns)
        return True

    def approve_deployment(
        self, proposal_id: str, operator_id: str, ts_ns: int
    ) -> bool:
        """Operator approves deployment for CLASS_B / CLASS_C proposals."""
        from evolution_engine.lifecycle.deployment import get_deployment_gate
        gate = get_deployment_gate()
        dr = gate.approve_deployment(proposal_id, operator_id, ts_ns)
        if dr is None:
            return False
        with self._lock:
            record = self._active.get(proposal_id)
            if record is None:
                return False
        record.deployment_record = dr
        record.add_audit("DEPLOYED", f"deployed by {operator_id}", operator_id, ts_ns)
        record.advance(LifecycleStage.DEPLOYED, f"deployed by {operator_id}", ts_ns)
        self._finalize(record, ts_ns)
        self._emit_transition(proposal_id, LifecycleStage.DEPLOYED, ts_ns)
        return True

    # ------------------------------------------------------------------
    # Read surface
    # ------------------------------------------------------------------

    def snapshot(self, limit: int = 20) -> dict[str, Any]:
        with self._lock:
            active = [r.to_dict() for r in self._active.values()]
            completed = [r.to_dict() for r in self._completed[-limit:]]
        return {
            "coordinator": "EvolutionLifecycleCoordinator",
            "tick_count": self._tick_count,
            "active_count": len(active),
            "completed_count": len(self._completed),
            "active": active,
            "recently_completed": completed,
        }

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        with self._lock:
            r = self._active.get(proposal_id)
            if r is None:
                for c in reversed(self._completed):
                    if c.proposal_id == proposal_id:
                        r = c
                        break
        return r.to_dict() if r else None

    # ------------------------------------------------------------------
    # Internal stage advancement
    # ------------------------------------------------------------------

    def _advance(self, record: ProposalRecord, ts_ns: int) -> bool:
        """Advance *record* one stage if it can proceed automatically.

        Returns True if a stage transition happened.
        """
        stage = record.stage

        if stage == LifecycleStage.PROPOSED:
            self._run_sandbox(record, ts_ns)
            return True

        if stage == LifecycleStage.SANDBOX:
            sr = record.sandbox_result
            if sr is not None and sr.outcome == "FAIL":
                self._reject(record, f"sandbox failed: {sr.notes}", ts_ns)
                return True
            if sr is not None:
                self._run_simulation(record, ts_ns)
                return True

        if stage == LifecycleStage.SIMULATION:
            simr = record.simulation_result
            if simr is not None and not simr.passed:
                self._reject(record, f"simulation failed (fitness={simr.fitness:.2f})", ts_ns)
                return True
            if simr is not None:
                self._run_benchmark(record, ts_ns)
                return True

        if stage == LifecycleStage.BENCHMARK:
            self._run_gov_review(record, ts_ns)
            return True

        if stage == LifecycleStage.GOV_REVIEW:
            # CLASS_A: auto-approve; B/C: wait for operator
            if self._auto_approve_a and record.mutation_class == "CLASS_A":
                from evolution_engine.lifecycle.contracts import GovernanceDecision
                decision = GovernanceDecision(
                    verdict="AUTO_APPROVED",
                    operator_id="AUTO",
                    reason="CLASS_A auto-approved",
                    ts_ns=ts_ns,
                )
                record.governance_decision = decision
                record.add_audit("GOV_REVIEW", "CLASS_A auto-approved", "AUTO", ts_ns)
                self._transition_to_promoted(record, ts_ns)
                return True
            return False  # awaiting operator

        if stage == LifecycleStage.PROMOTED:
            self._run_replay_audit(record, ts_ns)
            return True

        if stage == LifecycleStage.REPLAY_AUDIT:
            self._run_deployment(record, ts_ns)
            return True

        return False

    # ------------------------------------------------------------------
    # Stage executors (private, called only by _advance or operator API)
    # ------------------------------------------------------------------

    def _run_sandbox(self, record: ProposalRecord, ts_ns: int) -> None:
        from evolution_engine.lifecycle.sandbox import get_sandbox_runner
        result = get_sandbox_runner().run(record, ts_ns)
        record.sandbox_result = result
        record.advance(LifecycleStage.SANDBOX, f"sandbox={result.outcome}", ts_ns)
        record.add_audit("SANDBOX", f"outcome={result.outcome} {result.notes}", "SYSTEM", ts_ns)
        self._emit_transition(record.proposal_id, LifecycleStage.SANDBOX, ts_ns)

    def _run_simulation(self, record: ProposalRecord, ts_ns: int) -> None:
        from evolution_engine.lifecycle.simulation import get_simulation_evaluator
        result = get_simulation_evaluator().evaluate(record, ts_ns)
        record.simulation_result = result
        record.advance(
            LifecycleStage.SIMULATION,
            f"fitness={result.fitness:.2f} passed={result.passed}",
            ts_ns,
        )
        record.add_audit(
            "SIMULATION",
            f"fitness={result.fitness:.2f} rank={result.survivor_rank} passed={result.passed}",
            "SYSTEM",
            ts_ns,
        )
        self._emit_transition(record.proposal_id, LifecycleStage.SIMULATION, ts_ns)

    def _run_benchmark(self, record: ProposalRecord, ts_ns: int) -> None:
        from evolution_engine.lifecycle.benchmark import get_benchmark_engine
        result = get_benchmark_engine().run(record, ts_ns)
        record.benchmark_result = result
        record.advance(
            LifecycleStage.BENCHMARK,
            f"delta={result.delta_vs_baseline:+.4f} passed={result.passed}",
            ts_ns,
        )
        record.add_audit(
            "BENCHMARK",
            f"delta={result.delta_vs_baseline:+.4f} champion={result.champion_fitness:.2f}",
            "SYSTEM",
            ts_ns,
        )
        self._emit_transition(record.proposal_id, LifecycleStage.BENCHMARK, ts_ns)

    def _run_gov_review(self, record: ProposalRecord, ts_ns: int) -> None:
        record.advance(
            LifecycleStage.GOV_REVIEW,
            f"awaiting governance (class={record.mutation_class})",
            ts_ns,
        )
        record.add_audit(
            "GOV_REVIEW", f"gate opened class={record.mutation_class}", "SYSTEM", ts_ns
        )
        self._emit_transition(record.proposal_id, LifecycleStage.GOV_REVIEW, ts_ns)

    def _transition_to_promoted(self, record: ProposalRecord, ts_ns: int) -> None:
        from evolution_engine.lifecycle.rollback import get_rollback_engine
        snapshot_key = get_rollback_engine().register_for_rollback(record, ts_ns)
        record.advance(LifecycleStage.PROMOTED, f"promoted snapshot={snapshot_key[:12]}", ts_ns)
        record.add_audit("PROMOTED", f"promoted snapshot_key={snapshot_key}", "SYSTEM", ts_ns)
        self._emit_transition(record.proposal_id, LifecycleStage.PROMOTED, ts_ns)

    def _execute_rollback(
        self,
        record: ProposalRecord,
        trigger: str,
        operator_id: str,
        reason: str,
        ts_ns: int,
    ) -> None:
        from evolution_engine.lifecycle.rollback import get_rollback_engine
        rr = get_rollback_engine().execute_rollback(
            record, trigger=trigger, operator_id=operator_id, reason=reason, ts_ns=ts_ns
        )
        record.rollback_record = rr
        record.rolled_back = True
        record.advance(LifecycleStage.ROLLED_BACK, f"rollback trigger={trigger}", ts_ns)
        record.add_audit("ROLLED_BACK", f"trigger={trigger} by={operator_id}: {reason}",
                         operator_id, ts_ns)
        self._emit_transition(record.proposal_id, LifecycleStage.ROLLED_BACK, ts_ns)
        # Rolled-back proposals still go through REPLAY_AUDIT
        self._run_replay_audit(record, ts_ns)

    def _run_replay_audit(self, record: ProposalRecord, ts_ns: int) -> None:
        from evolution_engine.lifecycle.audit import get_replay_audit_trail
        trail = get_replay_audit_trail()
        trail.record_proposal(record)
        record.advance(LifecycleStage.REPLAY_AUDIT, "audit trail persisted", ts_ns)
        record.add_audit("REPLAY_AUDIT", "all stage decisions persisted", "SYSTEM", ts_ns)
        self._emit_transition(record.proposal_id, LifecycleStage.REPLAY_AUDIT, ts_ns)

        # Rolled-back proposals terminate here — no deployment
        if record.rolled_back:
            self._finalize(record, ts_ns)
            return
        # Otherwise, fall through to _run_deployment on next tick

    def _run_deployment(self, record: ProposalRecord, ts_ns: int) -> None:
        from evolution_engine.lifecycle.deployment import get_deployment_gate
        gate = get_deployment_gate(auto_deploy_class_a=self._auto_deploy_a)
        dr = gate.enter(record, ts_ns)
        if dr is not None:
            # Auto-approved
            record.deployment_record = dr
            record.add_audit("DEPLOYED", "auto-deployed via gate", "AUTO", ts_ns)
            record.advance(LifecycleStage.DEPLOYED, f"deployed gate={dr.gate_id}", ts_ns)
            self._finalize(record, ts_ns)
            self._emit_transition(record.proposal_id, LifecycleStage.DEPLOYED, ts_ns)
        # else: CLASS_B/C waiting for operator → approve_deployment()

    def _reject(self, record: ProposalRecord, reason: str, ts_ns: int) -> None:
        record.advance(LifecycleStage.REJECTED, reason, ts_ns)
        record.add_audit("REJECTED", reason, "SYSTEM", ts_ns)
        # Persist audit before finalising
        try:
            from evolution_engine.lifecycle.audit import get_replay_audit_trail
            get_replay_audit_trail().record_proposal(record)
        except Exception:
            pass
        self._finalize(record, ts_ns)
        self._emit_transition(record.proposal_id, LifecycleStage.REJECTED, ts_ns)

    def _finalize(self, record: ProposalRecord, ts_ns: int) -> None:
        with self._lock:
            self._active.pop(record.proposal_id, None)
            self._completed.append(record)
            if len(self._completed) > 500:
                self._completed = self._completed[-250:]

    # ------------------------------------------------------------------
    # Event emission
    # ------------------------------------------------------------------

    @staticmethod
    def _emit_transition(
        proposal_id: str, stage: LifecycleStage, ts_ns: int
    ) -> None:
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().publish(CognitiveChannel.DYON_PROPOSAL, {
                "proposal_id": proposal_id,
                "lifecycle_stage": stage.value,
                "lifecycle_coordinator": True,
                "ts_ns": ts_ns,
            })
        except Exception:
            pass
        try:
            from evolution_engine.charter.dyon_observability_emitter import emit_patch_proposal
            emit_patch_proposal(
                ts_ns=ts_ns,
                proposal_id=proposal_id,
                target_module="lifecycle_coordinator",
                patch_kind="LIFECYCLE_TRANSITION",
                description=f"Lifecycle stage → {stage.value}",
                rationale="evolution_lifecycle_coordinator",
                governance_status=stage.value,
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_coordinator: EvolutionLifecycleCoordinator | None = None
_coordinator_lock = threading.Lock()


def get_evolution_lifecycle_coordinator(
    *,
    max_active: int = 30,
    auto_approve_class_a: bool = True,
    auto_deploy_class_a: bool = True,
) -> EvolutionLifecycleCoordinator:
    """Return the process-wide EvolutionLifecycleCoordinator singleton.

    This is the ONLY authorised entry point for all mutation submissions.
    """
    global _coordinator
    with _coordinator_lock:
        if _coordinator is None:
            _coordinator = EvolutionLifecycleCoordinator(
                max_active=max_active,
                auto_approve_class_a=auto_approve_class_a,
                auto_deploy_class_a=auto_deploy_class_a,
            )
    return _coordinator


__all__ = [
    "EvolutionLifecycleCoordinator",
    "get_evolution_lifecycle_coordinator",
]

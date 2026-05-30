"""evolution_engine.lifecycle.contracts — Stage 7 lifecycle data contracts.

All inter-subsystem result types are frozen dataclasses (INV-08).
ProposalRecord is mutable — it accumulates stage results over its lifetime.

Stage sequence (closed loop):
  PROPOSED → SANDBOX → SIMULATION → BENCHMARK → GOV_REVIEW → PROMOTED
           → REPLAY_AUDIT → DEPLOYED          (happy path)
           → ROLLED_BACK → REPLAY_AUDIT       (exception path — no DEPLOYED)
  Any pre-PROMOTED stage can go → REJECTED.

"No direct uncontrolled mutation" is the governing constraint: every mutation
MUST enter via EvolutionLifecycleCoordinator.submit_proposal() and advance
only through coordinator.tick() / coordinator.approve_*() / coordinator.trigger_rollback().

Authority (L2/B1): stdlib only at module level.
INV-08: frozen=True, slots=True for all result types.
INV-15: ts_ns is caller-supplied everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


# ---------------------------------------------------------------------------
# Stage enum
# ---------------------------------------------------------------------------


class LifecycleStage(StrEnum):
    PROPOSED = "PROPOSED"
    SANDBOX = "SANDBOX"
    SIMULATION = "SIMULATION"
    BENCHMARK = "BENCHMARK"
    GOV_REVIEW = "GOV_REVIEW"
    PROMOTED = "PROMOTED"
    ROLLED_BACK = "ROLLED_BACK"
    REPLAY_AUDIT = "REPLAY_AUDIT"
    DEPLOYED = "DEPLOYED"
    REJECTED = "REJECTED"


# ---------------------------------------------------------------------------
# Stage result types (frozen / INV-08)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SandboxResult:
    """Isolated execution result from SandboxRunner."""

    outcome: str          # PASS | FAIL | SKIP
    notes: str
    elapsed_ms: float
    ts_ns: int


@dataclass(frozen=True, slots=True)
class SimulationResult:
    """Multi-scenario tournament fitness result from SimulationEvaluator."""

    fitness: float
    scenario_scores: dict[str, float]   # scenario_name → pnl_mean_usd
    tournament_id: str
    survivor_rank: int                  # 1 = best; 0 = not a survivor
    passed: bool                        # True if fitness ≥ threshold
    ts_ns: int


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    """Baseline comparison result from BenchmarkEngine."""

    delta_vs_baseline: float            # improvement (positive = better)
    champion_fitness: float             # current champion's fitness score
    passed: bool
    notes: str
    ts_ns: int


@dataclass(frozen=True, slots=True)
class GovernanceDecision:
    """Governance gate verdict from operator or auto-approval logic."""

    verdict: str                        # APPROVED | DENIED | DEFERRED | AUTO_APPROVED
    operator_id: str                    # "AUTO" for class-A
    reason: str
    ts_ns: int


@dataclass(frozen=True, slots=True)
class RollbackRecord:
    """Snapshot + trigger information for a rollback operation."""

    snapshot_key: str                   # identifies the pre-promotion snapshot
    trigger: str                        # OPERATOR | REGRESSION | WATCHDOG
    operator_id: str                    # "SYSTEM" if auto-triggered
    reason: str
    ts_ns: int


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """One deterministic replay-audit log entry."""

    stage: str
    note: str
    operator_id: str
    ts_ns: int


@dataclass(frozen=True, slots=True)
class DeploymentRecord:
    """Deployment gate clearance record."""

    gate_id: str
    approved_by: str
    deployment_hash: str
    mutation_class: str
    ts_ns: int


# ---------------------------------------------------------------------------
# Mutable proposal record
# ---------------------------------------------------------------------------


@dataclass
class ProposalRecord:
    """Mutable lifecycle record — accumulates results over the proposal's lifetime.

    Created by the coordinator at submission; only the coordinator mutates it.
    """

    proposal_id: str
    ts_ns_created: int
    description: str
    source_module: str
    mutation_class: str                      # CLASS_A | CLASS_B | CLASS_C

    stage: LifecycleStage = LifecycleStage.PROPOSED
    rolled_back: bool = False

    sandbox_result: SandboxResult | None = None
    simulation_result: SimulationResult | None = None
    benchmark_result: BenchmarkResult | None = None
    governance_decision: GovernanceDecision | None = None
    rollback_record: RollbackRecord | None = None
    deployment_record: DeploymentRecord | None = None

    audit_trail: list[AuditEntry] = field(default_factory=list)
    stage_log: list[dict[str, Any]] = field(default_factory=list)
    ts_ns_updated: int = 0

    # ------------------------------------------------------------------
    # Mutation helpers (only coordinator should call these)
    # ------------------------------------------------------------------

    def advance(self, stage: LifecycleStage, note: str, ts_ns: int) -> None:
        self.stage = stage
        self.ts_ns_updated = ts_ns
        self.stage_log.append({
            "stage": stage.value,
            "note": note,
            "ts_ns": ts_ns,
        })

    def add_audit(self, stage: str, note: str, operator_id: str, ts_ns: int) -> None:
        self.audit_trail.append(
            AuditEntry(stage=stage, note=note, operator_id=operator_id, ts_ns=ts_ns)
        )

    # ------------------------------------------------------------------
    # Read surface
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        sr = self.sandbox_result
        simr = self.simulation_result
        br = self.benchmark_result
        gd = self.governance_decision
        rr = self.rollback_record
        dr = self.deployment_record
        return {
            "proposal_id": self.proposal_id,
            "stage": self.stage.value,
            "mutation_class": self.mutation_class,
            "description": self.description,
            "source_module": self.source_module,
            "rolled_back": self.rolled_back,
            "sandbox": {
                "outcome": sr.outcome, "notes": sr.notes,
                "elapsed_ms": round(sr.elapsed_ms, 2),
            } if sr else None,
            "simulation": {
                "fitness": round(simr.fitness, 4),
                "passed": simr.passed,
                "survivor_rank": simr.survivor_rank,
                "tournament_id": simr.tournament_id,
                "scenario_scores": {k: round(v, 4) for k, v in simr.scenario_scores.items()},
            } if simr else None,
            "benchmark": {
                "delta_vs_baseline": round(br.delta_vs_baseline, 4),
                "champion_fitness": round(br.champion_fitness, 4),
                "passed": br.passed,
                "notes": br.notes,
            } if br else None,
            "governance": {
                "verdict": gd.verdict,
                "operator_id": gd.operator_id,
                "reason": gd.reason,
            } if gd else None,
            "rollback": {
                "snapshot_key": rr.snapshot_key,
                "trigger": rr.trigger,
                "operator_id": rr.operator_id,
                "reason": rr.reason,
            } if rr else None,
            "deployment": {
                "gate_id": dr.gate_id,
                "approved_by": dr.approved_by,
                "deployment_hash": dr.deployment_hash,
            } if dr else None,
            "audit_entries": len(self.audit_trail),
            "stage_count": len(self.stage_log),
            "ts_ns_created": self.ts_ns_created,
            "ts_ns_updated": self.ts_ns_updated,
        }


# ---------------------------------------------------------------------------
# Stage ordering helper
# ---------------------------------------------------------------------------

STAGE_ORDER: list[LifecycleStage] = [
    LifecycleStage.PROPOSED,
    LifecycleStage.SANDBOX,
    LifecycleStage.SIMULATION,
    LifecycleStage.BENCHMARK,
    LifecycleStage.GOV_REVIEW,
    LifecycleStage.PROMOTED,
    LifecycleStage.REPLAY_AUDIT,
    LifecycleStage.DEPLOYED,
]

TERMINAL_STAGES: frozenset[LifecycleStage] = frozenset({
    LifecycleStage.DEPLOYED,
    LifecycleStage.ROLLED_BACK,
    LifecycleStage.REJECTED,
})


__all__ = [
    "AuditEntry",
    "BenchmarkResult",
    "DeploymentRecord",
    "GovernanceDecision",
    "LifecycleStage",
    "ProposalRecord",
    "RollbackRecord",
    "STAGE_ORDER",
    "TERMINAL_STAGES",
    "SandboxResult",
    "SimulationResult",
]

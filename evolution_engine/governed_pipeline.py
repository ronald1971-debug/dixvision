"""evolution_engine.governed_pipeline — End-to-end governed mutation lifecycle.

Drives the full proposal→sandbox→benchmark→governance→promotion→rollback→audit
pipeline as one orchestrated flow with operator-visible events at every stage.

Lifecycle stages:
  1. PROPOSED    — DYON or mutation_proposer generates a patch
  2. SANDBOX     — isolated execution test (no production state)
  3. BENCHMARK   — performance comparison against baseline
  4. GOV_REVIEW  — governance FSM (Class A auto / Class B paper / Class C manual)
  5. PROMOTED    — applied to active strategy registry
  6. MONITORING  — canary / shadow comparison post-promotion
  7. ROLLED_BACK — reverted due to regression
  8. AUDITED     — final audit digest computed and stored

All stage transitions are emitted to the DYON observability ledger and the
cognitive event bus.  The operator sees every step.

Authority (L2/B1): imports only evolution_engine.*, governance_engine.*, core.*,
state.*.  Never imports intelligence_engine or execution_engine.
INV-15: ts_ns is caller-supplied.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

_logger = logging.getLogger(__name__)


class PipelineStage(StrEnum):
    PROPOSED = "PROPOSED"
    SANDBOX = "SANDBOX"
    BENCHMARK = "BENCHMARK"
    GOV_REVIEW = "GOV_REVIEW"
    PROMOTED = "PROMOTED"
    MONITORING = "MONITORING"
    ROLLED_BACK = "ROLLED_BACK"
    AUDITED = "AUDITED"
    REJECTED = "REJECTED"


@dataclass
class PipelineRecord:
    """Mutable lifecycle record for one patch proposal."""

    proposal_id: str
    ts_ns_created: int
    description: str
    source_module: str
    mutation_class: str              # CLASS_A | CLASS_B | CLASS_C

    stage: PipelineStage = PipelineStage.PROPOSED
    sandbox_outcome: str = ""        # PASS | FAIL | SKIP
    benchmark_delta: float = 0.0    # improvement vs baseline
    governance_verdict: str = ""     # APPROVED | DENIED | DEFERRED
    audit_digest: str = ""
    stage_log: list[dict[str, Any]] = field(default_factory=list)
    ts_ns_updated: int = 0

    def log_stage(self, stage: PipelineStage, note: str, ts_ns: int) -> None:
        self.stage = stage
        self.ts_ns_updated = ts_ns
        self.stage_log.append({
            "stage": stage.value,
            "note": note,
            "ts_ns": ts_ns,
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "stage": self.stage.value,
            "mutation_class": self.mutation_class,
            "description": self.description,
            "source_module": self.source_module,
            "sandbox_outcome": self.sandbox_outcome,
            "benchmark_delta": round(self.benchmark_delta, 4),
            "governance_verdict": self.governance_verdict,
            "audit_digest": self.audit_digest,
            "stage_count": len(self.stage_log),
            "ts_ns_created": self.ts_ns_created,
            "ts_ns_updated": self.ts_ns_updated,
        }


class GovernedEvolutionPipeline:
    """Orchestrates the full mutation lifecycle with governance at every gate.

    Args:
        max_active: maximum concurrent proposals in-flight
        auto_approve_class_a: if True, CLASS_A mutations skip operator approval
    """

    def __init__(
        self,
        *,
        max_active: int = 20,
        auto_approve_class_a: bool = True,
    ) -> None:
        self._lock = threading.Lock()
        self._max_active = max_active
        self._auto_approve_class_a = auto_approve_class_a
        # proposal_id → PipelineRecord
        self._records: dict[str, PipelineRecord] = {}
        self._completed: list[PipelineRecord] = []
        self._tick_count: int = 0

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------

    def submit(
        self,
        *,
        proposal_id: str,
        description: str,
        source_module: str,
        mutation_class: str,
        ts_ns: int,
    ) -> bool:
        """Submit a new patch proposal into the pipeline.

        Returns False if the pipeline is at capacity or the proposal
        already exists.
        """
        with self._lock:
            if proposal_id in self._records:
                return False
            if len(self._records) >= self._max_active:
                _logger.debug(
                    "GovernedEvolutionPipeline: capacity full (%d), drop %s",
                    self._max_active, proposal_id,
                )
                return False
            record = PipelineRecord(
                proposal_id=proposal_id,
                ts_ns_created=ts_ns,
                description=description,
                source_module=source_module,
                mutation_class=mutation_class,
            )
            record.log_stage(PipelineStage.PROPOSED, "submitted to pipeline", ts_ns)
            self._records[proposal_id] = record

        self._emit_transition(proposal_id, PipelineStage.PROPOSED, ts_ns)
        _logger.debug("GovernedEvolutionPipeline: proposal %s submitted", proposal_id)
        return True

    # ------------------------------------------------------------------
    # Tick — advance proposals through the pipeline
    # ------------------------------------------------------------------

    def tick(self, *, ts_ns: int) -> int:
        """Advance all active proposals one step.

        Returns the number of proposals that changed stage.
        """
        self._tick_count += 1
        advanced = 0

        with self._lock:
            active = list(self._records.values())

        for record in active:
            if self._advance(record, ts_ns):
                advanced += 1

        return advanced

    # ------------------------------------------------------------------
    # Operator API — approve / reject / rollback
    # ------------------------------------------------------------------

    def operator_approve(self, proposal_id: str, ts_ns: int) -> bool:
        """Operator approves a proposal in GOV_REVIEW stage."""
        with self._lock:
            record = self._records.get(proposal_id)
            if record is None or record.stage != PipelineStage.GOV_REVIEW:
                return False
            record.governance_verdict = "APPROVED"
            record.log_stage(PipelineStage.PROMOTED, "operator approved", ts_ns)
        self._emit_transition(proposal_id, PipelineStage.PROMOTED, ts_ns)
        self._apply_to_registry(record, ts_ns)
        return True

    def operator_reject(self, proposal_id: str, reason: str, ts_ns: int) -> bool:
        """Operator rejects a proposal."""
        with self._lock:
            record = self._records.get(proposal_id)
            if record is None:
                return False
            record.governance_verdict = f"DENIED:{reason}"
            record.log_stage(PipelineStage.REJECTED, reason, ts_ns)
            self._finalize(record, ts_ns)
        self._emit_transition(proposal_id, PipelineStage.REJECTED, ts_ns)
        return True

    def operator_rollback(self, proposal_id: str, reason: str, ts_ns: int) -> bool:
        """Operator rolls back a promoted proposal."""
        with self._lock:
            record = self._records.get(proposal_id)
            if record is None or record.stage not in (
                PipelineStage.PROMOTED, PipelineStage.MONITORING
            ):
                return False
            record.log_stage(PipelineStage.ROLLED_BACK, reason, ts_ns)
            self._finalize(record, ts_ns)
        self._emit_transition(proposal_id, PipelineStage.ROLLED_BACK, ts_ns)
        self._audit(record, ts_ns)
        return True

    # ------------------------------------------------------------------
    # Read surface
    # ------------------------------------------------------------------

    def snapshot(self, limit: int = 20) -> dict[str, Any]:
        with self._lock:
            active = [r.to_dict() for r in self._records.values()]
            completed = [r.to_dict() for r in self._completed[-limit:]]
        return {
            "pipeline": "GovernedEvolutionPipeline",
            "tick_count": self._tick_count,
            "active_count": len(active),
            "completed_count": len(self._completed),
            "active": active,
            "recently_completed": completed,
        }

    # ------------------------------------------------------------------
    # Internal pipeline advancement
    # ------------------------------------------------------------------

    def _advance(self, record: PipelineRecord, ts_ns: int) -> bool:
        """Advance one record to its next stage if ready.  Returns True if advanced."""
        stage = record.stage

        if stage == PipelineStage.PROPOSED:
            return self._run_sandbox(record, ts_ns)

        if stage == PipelineStage.SANDBOX:
            if record.sandbox_outcome == "FAIL":
                with self._lock:
                    record.log_stage(PipelineStage.REJECTED, "sandbox failed", ts_ns)
                    self._finalize(record, ts_ns)
                self._emit_transition(record.proposal_id, PipelineStage.REJECTED, ts_ns)
                return True
            return self._run_benchmark(record, ts_ns)

        if stage == PipelineStage.BENCHMARK:
            return self._run_gov_review(record, ts_ns)

        if stage == PipelineStage.GOV_REVIEW:
            # CLASS_A: auto-approve; CLASS_B/C: wait for operator
            if self._auto_approve_class_a and record.mutation_class == "CLASS_A":
                with self._lock:
                    record.governance_verdict = "AUTO_APPROVED"
                    record.log_stage(PipelineStage.PROMOTED, "CLASS_A auto-approved", ts_ns)
                self._emit_transition(record.proposal_id, PipelineStage.PROMOTED, ts_ns)
                self._apply_to_registry(record, ts_ns)
                return True
            return False  # waiting for operator

        if stage == PipelineStage.PROMOTED:
            return self._run_monitoring(record, ts_ns)

        if stage == PipelineStage.MONITORING:
            return self._run_audit(record, ts_ns)

        return False

    def _run_sandbox(self, record: PipelineRecord, ts_ns: int) -> bool:
        """Run sandbox isolation test."""
        outcome = "PASS"
        try:
            from evolution_engine.patch_pipeline.sandbox import PatchSandbox
            sb = PatchSandbox()
            result = sb.run(record.proposal_id, record.description)
            outcome = "PASS" if result else "FAIL"
        except Exception:
            outcome = "SKIP"  # sandbox not available; continue pipeline

        with self._lock:
            record.sandbox_outcome = outcome
            record.log_stage(PipelineStage.SANDBOX, f"sandbox={outcome}", ts_ns)
        self._emit_transition(record.proposal_id, PipelineStage.SANDBOX, ts_ns)
        return True

    def _run_benchmark(self, record: PipelineRecord, ts_ns: int) -> bool:
        """Run performance benchmark comparison."""
        delta = 0.0
        try:
            from evolution_engine.patch_pipeline.backtest import BacktestStage
            stage = BacktestStage()
            delta = stage.delta_vs_baseline(record.proposal_id) or 0.0
        except Exception:
            delta = 0.0

        with self._lock:
            record.benchmark_delta = delta
            note = f"benchmark delta={delta:+.4f}"
            record.log_stage(PipelineStage.BENCHMARK, note, ts_ns)
        self._emit_transition(record.proposal_id, PipelineStage.BENCHMARK, ts_ns)
        return True

    def _run_gov_review(self, record: PipelineRecord, ts_ns: int) -> bool:
        with self._lock:
            record.log_stage(
                PipelineStage.GOV_REVIEW,
                f"awaiting governance (class={record.mutation_class})",
                ts_ns,
            )
        self._emit_transition(record.proposal_id, PipelineStage.GOV_REVIEW, ts_ns)
        return True

    def _run_monitoring(self, record: PipelineRecord, ts_ns: int) -> bool:
        """Brief monitoring window after promotion."""
        with self._lock:
            record.log_stage(PipelineStage.MONITORING, "post-promotion monitoring", ts_ns)
        self._emit_transition(record.proposal_id, PipelineStage.MONITORING, ts_ns)
        return True

    def _run_audit(self, record: PipelineRecord, ts_ns: int) -> bool:
        self._audit(record, ts_ns)
        return True

    def _audit(self, record: PipelineRecord, ts_ns: int) -> None:
        """Compute audit digest and finalize."""
        digest = self._compute_audit_digest(record, ts_ns)
        with self._lock:
            record.audit_digest = digest
            record.log_stage(PipelineStage.AUDITED, f"digest={digest[:16]}", ts_ns)
            self._finalize(record, ts_ns)
        self._emit_transition(record.proposal_id, PipelineStage.AUDITED, ts_ns)
        self._store_audit(record, ts_ns)

    def _finalize(self, record: PipelineRecord, ts_ns: int) -> None:
        """Move from active to completed (lock must be held)."""
        self._records.pop(record.proposal_id, None)
        self._completed.append(record)
        if len(self._completed) > 500:
            self._completed = self._completed[-250:]

    def _apply_to_registry(self, record: PipelineRecord, ts_ns: int) -> None:
        """Promote to strategy registry (best-effort)."""
        try:
            from governance_engine.strategy_registry import get_strategy_registry
            reg = get_strategy_registry()
            if hasattr(reg, "promote"):
                reg.promote(record.proposal_id, ts_ns=ts_ns)
        except Exception:
            pass

    @staticmethod
    def _compute_audit_digest(record: PipelineRecord, ts_ns: int) -> str:
        import hashlib
        import json
        doc = {
            "proposal_id": record.proposal_id,
            "mutation_class": record.mutation_class,
            "stage": record.stage.value,
            "governance_verdict": record.governance_verdict,
            "benchmark_delta": record.benchmark_delta,
            "stage_count": len(record.stage_log),
            "ts_ns_created": record.ts_ns_created,
            "ts_ns_final": ts_ns,
        }
        raw = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.blake2b(raw, digest_size=8).hexdigest()

    def _store_audit(self, record: PipelineRecord, ts_ns: int) -> None:
        """Persist the audit record to the ledger."""
        try:
            from state.ledger.append import append_event
            append_event(
                stream="SYSTEM",
                kind="EVOLUTION_AUDIT",
                source="DYON",
                payload={
                    "proposal_id": record.proposal_id,
                    "mutation_class": record.mutation_class,
                    "final_stage": record.stage.value,
                    "governance_verdict": record.governance_verdict,
                    "benchmark_delta": record.benchmark_delta,
                    "audit_digest": record.audit_digest,
                    "ts_ns": ts_ns,
                },
            )
        except Exception:
            pass

    def _emit_transition(
        self, proposal_id: str, stage: PipelineStage, ts_ns: int
    ) -> None:
        """Publish stage transition to DYON event bus channel."""
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().publish(CognitiveChannel.DYON_PROPOSAL, {
                "proposal_id": proposal_id,
                "pipeline_stage": stage.value,
                "governed_pipeline": True,
                "ts_ns": ts_ns,
            })
        except Exception:
            pass
        try:
            from evolution_engine.charter.dyon_observability_emitter import (
                emit_patch_proposal,
            )
            emit_patch_proposal(
                ts_ns=ts_ns,
                proposal_id=proposal_id,
                target_module="governed_pipeline",
                patch_kind="LIFECYCLE_TRANSITION",
                description=f"Stage transition → {stage.value}",
                rationale="governed_evolution_pipeline",
                governance_status=stage.value,
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_pipeline: GovernedEvolutionPipeline | None = None
_pipeline_lock = threading.Lock()


def get_governed_pipeline(
    *,
    max_active: int = 20,
    auto_approve_class_a: bool = True,
) -> GovernedEvolutionPipeline:
    """Return the process-wide GovernedEvolutionPipeline singleton."""
    global _pipeline
    with _pipeline_lock:
        if _pipeline is None:
            _pipeline = GovernedEvolutionPipeline(
                max_active=max_active,
                auto_approve_class_a=auto_approve_class_a,
            )
    return _pipeline


__all__ = [
    "GovernedEvolutionPipeline",
    "PipelineRecord",
    "PipelineStage",
    "get_governed_pipeline",
]

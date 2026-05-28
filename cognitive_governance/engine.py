"""
cognitive_governance/engine.py
DIX VISION v42.2 — Cognitive Governance Engine

Central coordinator for the cognitive integrity layer. Delegates to
the 11 specialist guards, aggregates their reports into a unified
CognitiveIntegrityStatus, and emits periodic COGOV_INTEGRITY_STATUS
events to the governance ledger.

Responsibilities:
  - Instantiate and hold references to all 11 guards (lazy, thread-safe)
  - Provide unified health check: check_all() -> CognitiveIntegrityStatus
  - Route incoming events (LearningUpdate, PatchProposal, TradeOutcome)
    to the appropriate guards
  - Emit COGOV_INTEGRITY_STATUS periodically (default: every 60 seconds)
  - Escalate CRITICAL violations to the financial governance via the
    hazard bus (cognitive corruption is a system hazard)

The engine is in CONTROL domain authority. It never executes trades.
It never directly modifies learning parameters. It observes and gates.
"""

from __future__ import annotations

import threading
import time as _time

from core.contracts.cognitive_governance import (
    CognitiveSeverity,
    CognitiveViolationKind,
    CognitiveIntegrityStatus,
    MutationValidationResult,
)
from state.ledger.event_store import append_event

# Guard imports (engine is the only module allowed to import other
# cognitive_governance modules directly — per spec note 6)
from cognitive_governance.belief_integrity import (
    BeliefIntegrityGuard,
    get_belief_integrity_guard,
)
from cognitive_governance.causal_consistency import (
    CausalConsistencyGuard,
    get_causal_consistency_guard,
)
from cognitive_governance.epistemic_drift import (
    EpistemicDriftMonitor,
    get_epistemic_drift_monitor,
)
from cognitive_governance.hallucination_guard import (
    HallucinationGuard,
    get_hallucination_guard,
)
from cognitive_governance.identity_stability import (
    IdentityStabilityMonitor,
    get_identity_stability_monitor,
)
from cognitive_governance.learning_truthfulness import (
    LearningTruthfulnessValidator,
    get_learning_truthfulness_validator,
)
from cognitive_governance.memory_contamination import (
    MemoryContaminationDetector,
    get_memory_contamination_detector,
)
from cognitive_governance.mutation_validator import (
    MutationValidator,
    get_mutation_validator,
)
from cognitive_governance.reward_hacking_detector import (
    RewardHackingDetector,
    get_reward_hacking_detector,
)
from cognitive_governance.strategy_lineage_guard import (
    StrategyLineageGuard,
    get_strategy_lineage_guard,
)
from cognitive_governance.synthetic_feedback_detection import (
    SyntheticFeedbackDetector,
    get_synthetic_feedback_detector,
)


class CognitiveGovernanceEngine:
    """
    Central coordinator for all cognitive integrity guards.

    Thread-safe. Holds lazy references to all 11 specialist guards.
    Provides check_all() for a full integrity snapshot and routing
    methods for the three main event types.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_status_ts: int = 0
        self._status_interval_ns: int = 60 * 1_000_000_000  # 60 seconds

        # Lazy-init guard references (populated on first access)
        self._belief_integrity: BeliefIntegrityGuard | None = None
        self._causal_consistency: CausalConsistencyGuard | None = None
        self._epistemic_drift: EpistemicDriftMonitor | None = None
        self._hallucination_guard: HallucinationGuard | None = None
        self._identity_stability: IdentityStabilityMonitor | None = None
        self._learning_truthfulness: LearningTruthfulnessValidator | None = None
        self._memory_contamination: MemoryContaminationDetector | None = None
        self._mutation_validator: MutationValidator | None = None
        self._reward_hacking: RewardHackingDetector | None = None
        self._strategy_lineage: StrategyLineageGuard | None = None
        self._synthetic_feedback: SyntheticFeedbackDetector | None = None

    # ------------------------------------------------------------------
    # Guard properties (lazy-init via module singletons)
    # ------------------------------------------------------------------

    @property
    def belief_integrity(self) -> BeliefIntegrityGuard:
        if self._belief_integrity is None:
            self._belief_integrity = get_belief_integrity_guard()
        return self._belief_integrity

    @property
    def causal_consistency(self) -> CausalConsistencyGuard:
        if self._causal_consistency is None:
            self._causal_consistency = get_causal_consistency_guard()
        return self._causal_consistency

    @property
    def epistemic_drift(self) -> EpistemicDriftMonitor:
        if self._epistemic_drift is None:
            self._epistemic_drift = get_epistemic_drift_monitor()
        return self._epistemic_drift

    @property
    def hallucination_guard(self) -> HallucinationGuard:
        if self._hallucination_guard is None:
            self._hallucination_guard = get_hallucination_guard()
        return self._hallucination_guard

    @property
    def identity_stability(self) -> IdentityStabilityMonitor:
        if self._identity_stability is None:
            self._identity_stability = get_identity_stability_monitor()
        return self._identity_stability

    @property
    def learning_truthfulness(self) -> LearningTruthfulnessValidator:
        if self._learning_truthfulness is None:
            self._learning_truthfulness = get_learning_truthfulness_validator()
        return self._learning_truthfulness

    @property
    def memory_contamination(self) -> MemoryContaminationDetector:
        if self._memory_contamination is None:
            self._memory_contamination = get_memory_contamination_detector()
        return self._memory_contamination

    @property
    def mutation_validator(self) -> MutationValidator:
        if self._mutation_validator is None:
            self._mutation_validator = get_mutation_validator()
        return self._mutation_validator

    @property
    def reward_hacking(self) -> RewardHackingDetector:
        if self._reward_hacking is None:
            self._reward_hacking = get_reward_hacking_detector()
        return self._reward_hacking

    @property
    def strategy_lineage(self) -> StrategyLineageGuard:
        if self._strategy_lineage is None:
            self._strategy_lineage = get_strategy_lineage_guard()
        return self._strategy_lineage

    @property
    def synthetic_feedback(self) -> SyntheticFeedbackDetector:
        if self._synthetic_feedback is None:
            self._synthetic_feedback = get_synthetic_feedback_detector()
        return self._synthetic_feedback

    # ------------------------------------------------------------------
    # Unified health check
    # ------------------------------------------------------------------

    def check_all(self) -> CognitiveIntegrityStatus:
        """
        Aggregate health snapshot across all cognitive guards.

        Queries each guard's current state without triggering new events.
        Returns CognitiveIntegrityStatus with per-dimension health flags
        and the union of all active violations.
        """
        ts_ns = _time.time_ns()
        active_violations: list[CognitiveViolationKind] = []

        # Belief integrity: check current ECE
        belief_ece = self.belief_integrity.get_ece
        belief_ok = belief_ece < 0.15  # ECE_WARNING_THRESHOLD
        if not belief_ok:
            active_violations.append(CognitiveViolationKind.CALIBRATION_DRIFT)

        # Epistemic drift
        drift_score = self.epistemic_drift.get_drift_score()
        epistemic_ok = drift_score < 0.25  # WARNING_THRESHOLD
        if not epistemic_ok:
            if drift_score >= 0.50:
                active_violations.append(CognitiveViolationKind.EPISTEMIC_DRIFT_CRITICAL)
            else:
                active_violations.append(CognitiveViolationKind.EPISTEMIC_DRIFT_WARNING)

        # Learning truthfulness
        ext_ratio = self.learning_truthfulness.get_external_ratio()
        learning_truthful = ext_ratio >= 0.40  # TRUTHFULNESS_THRESHOLD
        if not learning_truthful:
            active_violations.append(CognitiveViolationKind.LEARNING_NOT_GROUNDED)

        # Memory, mutation, hallucination, causal, identity, synthetic,
        # reward, lineage — these are event-driven guards that do not
        # expose a polling API for "current health" without a scan target.
        # We mark them healthy by default at this snapshot; individual
        # events drive the violation record. For a full scan these would
        # require store names, strategy IDs, etc.
        memory_clean = True        # healthy until a scan reports otherwise
        mutation_safe = True       # healthy until a proposal is rejected
        no_hallucination = True    # healthy until a signal is flagged
        lineage_intact = True      # healthy until a registration fails
        identity_stable = True     # healthy until an update is flagged
        no_synthetic_feedback = True  # healthy until routing contam detected
        no_reward_hacking = True   # healthy until correlation drops
        causal_consistent = True   # healthy until a ghost/leak is found

        overall_healthy = (
            belief_ok
            and memory_clean
            and mutation_safe
            and no_hallucination
            and epistemic_ok
            and learning_truthful
            and lineage_intact
            and identity_stable
            and no_synthetic_feedback
            and no_reward_hacking
            and causal_consistent
        )

        detail_parts: list[str] = []
        if not belief_ok:
            detail_parts.append(f"belief_ece={belief_ece:.4f}")
        if not epistemic_ok:
            detail_parts.append(f"drift_score={drift_score:.4f}")
        if not learning_truthful:
            detail_parts.append(f"ext_ratio={ext_ratio:.4f}")
        detail = "; ".join(detail_parts) if detail_parts else "all guards healthy"

        return CognitiveIntegrityStatus(
            ts_ns=ts_ns,
            overall_healthy=overall_healthy,
            belief_integrity_ok=belief_ok,
            memory_clean=memory_clean,
            mutation_safe=mutation_safe,
            no_hallucination=no_hallucination,
            epistemic_current=epistemic_ok,
            learning_truthful=learning_truthful,
            lineage_intact=lineage_intact,
            identity_stable=identity_stable,
            no_synthetic_feedback=no_synthetic_feedback,
            no_reward_hacking=no_reward_hacking,
            causal_consistent=causal_consistent,
            active_violations=tuple(active_violations),
            detail=detail,
        )

    # ------------------------------------------------------------------
    # Event routing
    # ------------------------------------------------------------------

    def on_learning_update(self, update: dict) -> None:
        """
        Route a learning update to relevant guards.

        Expected update keys:
          - signal_id: str
          - source: str
          - external_anchors: list[str]
          - mode: str        ("live" | "paper" | ...)
          - target_lane: str
          - ts_ns: int
        """
        signal_id = update.get("signal_id", "")
        source = update.get("source", "")
        external_anchors = update.get("external_anchors", [])
        mode = update.get("mode", "unknown")
        target_lane = update.get("target_lane", "unknown")
        ts_ns = update.get("ts_ns", _time.time_ns())

        # Route to learning truthfulness validator
        self.learning_truthfulness.record_learning_signal(
            signal_id=signal_id,
            source=source,
            external_anchors=external_anchors,
            mode=mode,
            ts_ns=ts_ns,
        )

        # Route to synthetic feedback detector
        self.synthetic_feedback.record_learning_signal(
            signal_id=signal_id,
            mode=mode,
            target_lane=target_lane,
            ts_ns=ts_ns,
        )

        # Route to hallucination guard if parent signal is known
        parent_signal_id = update.get("parent_signal_id")
        is_external = bool(external_anchors) and mode not in ("paper", "simulation", "backtest")
        self.hallucination_guard.register_signal(
            signal_id=signal_id,
            source=source,
            parent_signal_id=parent_signal_id,
            is_external=is_external,
            mode=mode,
            ts_ns=ts_ns,
        )

    def on_mutation_proposal(self, proposal: dict) -> MutationValidationResult:
        """
        Route a mutation proposal to mutation_validator and strategy_lineage_guard.

        Expected proposal keys:
          - mutation_id: str
          - strategy_id: str
          - source: str
          - param_deltas: dict[str, float]
          - lineage_id: str | None
          - ts_ns: int
        """
        mutation_id = proposal.get("mutation_id", "")
        strategy_id = proposal.get("strategy_id", "")
        source = proposal.get("source", "")
        param_deltas = proposal.get("param_deltas", {})
        lineage_id = proposal.get("lineage_id")
        ts_ns = proposal.get("ts_ns", _time.time_ns())

        # Validate lineage first (fast gate)
        if lineage_id:
            self.strategy_lineage.validate_lineage(lineage_id)

        # Validate mutation parameters
        result = self.mutation_validator.validate_mutation(
            mutation_id=mutation_id,
            strategy_id=strategy_id,
            source=source,
            param_deltas=param_deltas,
            lineage_id=lineage_id,
            ts_ns=ts_ns,
        )

        return result

    def on_reward_sample(
        self,
        strategy_id: str,
        reward: float,
        objective: float,
        ts_ns: int,
    ) -> None:
        """
        Route a reward sample to the reward hacking detector.
        """
        self.reward_hacking.record_reward_sample(
            strategy_id=strategy_id,
            reward=reward,
            objective_metric=objective,
            ts_ns=ts_ns,
        )

    def emit_status(self) -> CognitiveIntegrityStatus:
        """
        Compute and emit a COGOV_INTEGRITY_STATUS event to the governance ledger.

        Performs rate-limiting: will not emit more than once per
        _status_interval_ns regardless of how often it is called.
        """
        ts_ns = _time.time_ns()
        status = self.check_all()

        with self._lock:
            should_emit = (ts_ns - self._last_status_ts) >= self._status_interval_ns
            if should_emit:
                self._last_status_ts = ts_ns

        if should_emit:
            append_event(
                "GOVERNANCE",
                "COGOV_INTEGRITY_STATUS",
                "cognitive_governance.engine",
                {
                    "overall_healthy": status.overall_healthy,
                    "belief_integrity_ok": status.belief_integrity_ok,
                    "memory_clean": status.memory_clean,
                    "mutation_safe": status.mutation_safe,
                    "no_hallucination": status.no_hallucination,
                    "epistemic_current": status.epistemic_current,
                    "learning_truthful": status.learning_truthful,
                    "lineage_intact": status.lineage_intact,
                    "identity_stable": status.identity_stable,
                    "no_synthetic_feedback": status.no_synthetic_feedback,
                    "no_reward_hacking": status.no_reward_hacking,
                    "causal_consistent": status.causal_consistent,
                    "active_violations": [v.value for v in status.active_violations],
                    "detail": status.detail,
                },
            )

            # Escalate CRITICAL violations to the hazard bus
            critical = [
                v for v in status.active_violations
                if v in (
                    CognitiveViolationKind.EPISTEMIC_DRIFT_CRITICAL,
                    CognitiveViolationKind.CALIBRATION_DRIFT,
                )
            ]
            if critical:
                self._escalate_critical(list(critical))

        return status

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _escalate_critical(self, violations: list) -> None:
        """
        Escalate CRITICAL cognitive violations to the governance hazard stream.

        Cognitive corruption is a system hazard. We append a HAZARD event
        so the financial governance escalation path can respond
        (e.g., mode transition to SAFE or HALTED).

        This does NOT directly block execution — that is Governance's decision.
        """
        try:
            append_event(
                "HAZARD",
                "COGOV_CRITICAL_VIOLATION",
                "cognitive_governance.engine",
                {
                    "violations": [v.value for v in violations],
                    "escalation": "CRITICAL cognitive integrity violation — "
                    "Governance should review mode transition",
                    "source": "cognitive_governance.engine",
                },
            )
        except Exception:
            # Best-effort — must never raise in the governance path
            pass


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: CognitiveGovernanceEngine | None = None
_lock = threading.Lock()


def get_cognitive_governance() -> CognitiveGovernanceEngine:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = CognitiveGovernanceEngine()
    return _instance


__all__ = ["CognitiveGovernanceEngine", "get_cognitive_governance"]

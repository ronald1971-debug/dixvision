"""
core/contracts/cognitive_governance.py
DIX VISION v42.2 — Cognitive Governance contract types.

These records cross the boundary between the learning/evolution engines
and the cognitive governance control plane. Like all core.contracts
they are frozen, slotted, replay-deterministic value objects (INV-08,
INV-15). No callables, no IO.

Cognitive Governance protects four complementary integrity properties:

  1. Belief Integrity         — convictions are calibrated and causally grounded
  2. Memory Integrity         — vector stores haven't drifted or been contaminated
  3. Mutation Safety          — strategy evolution stays within reversible bounds
  4. Epistemic Honesty        — learning is grounded in external observation,
                               not synthetic feedback or reward gaming

These protections ARE the P0 safety layer during Phase 0–3 (cognitive
build-out). Capital protection (FinancialGovernance) becomes co-equal in
Phase 4+ once live execution is real.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class CognitiveViolationKind(StrEnum):
    OVERCONFIDENCE          = "OVERCONFIDENCE"
    CALIBRATION_DRIFT       = "CALIBRATION_DRIFT"
    MAGICAL_BELIEF_JUMP     = "MAGICAL_BELIEF_JUMP"
    MEMORY_CONTAMINATION    = "MEMORY_CONTAMINATION"
    EMBEDDING_COLLAPSE      = "EMBEDDING_COLLAPSE"
    MUTATION_OUT_OF_BUDGET  = "MUTATION_OUT_OF_BUDGET"
    MUTATION_IRREVERSIBLE   = "MUTATION_IRREVERSIBLE"
    LINEAGE_GAP             = "LINEAGE_GAP"
    LINEAGE_CYCLE           = "LINEAGE_CYCLE"
    HALLUCINATION_LOOP      = "HALLUCINATION_LOOP"
    SELF_REFERENTIAL_REWARD = "SELF_REFERENTIAL_REWARD"
    EPISTEMIC_DRIFT_WARNING = "EPISTEMIC_DRIFT_WARNING"
    EPISTEMIC_DRIFT_CRITICAL= "EPISTEMIC_DRIFT_CRITICAL"
    SYNTHETIC_FEEDBACK      = "SYNTHETIC_FEEDBACK"
    REWARD_HACKING          = "REWARD_HACKING"
    IDENTITY_INSTABILITY    = "IDENTITY_INSTABILITY"
    CAUSAL_GHOST            = "CAUSAL_GHOST"
    CAUSAL_DOMAIN_LEAK      = "CAUSAL_DOMAIN_LEAK"
    LEARNING_NOT_GROUNDED   = "LEARNING_NOT_GROUNDED"


class CognitiveSeverity(StrEnum):
    INFO     = "INFO"
    WARNING  = "WARNING"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True, slots=True)
class BeliefIntegrityReport:
    """Result of a belief-update validation check."""
    ts_ns: int
    belief_id: str
    source: str
    passed: bool
    severity: CognitiveSeverity = CognitiveSeverity.INFO
    violations: tuple[CognitiveViolationKind, ...] = ()
    confidence_score: float = 1.0
    calibration_error: float = 0.0
    detail: str = ""


@dataclass(frozen=True, slots=True)
class MemoryContaminationReport:
    """Result of a vector-memory health scan."""
    ts_ns: int
    store_name: str
    passed: bool
    contamination_score: float      # 0.0 = clean … 1.0 = fully contaminated
    drift_rate_per_hour: float
    anomalous_clusters: int
    severity: CognitiveSeverity = CognitiveSeverity.INFO
    violations: tuple[CognitiveViolationKind, ...] = ()
    detail: str = ""


@dataclass(frozen=True, slots=True)
class MutationValidationResult:
    """Gate result for a proposed strategy mutation."""
    ts_ns: int
    mutation_id: str
    source: str
    approved: bool
    reversible: bool = True
    scope_exceeded: bool = False
    violations: tuple[CognitiveViolationKind, ...] = ()
    detail: str = ""


@dataclass(frozen=True, slots=True)
class HallucinationReport:
    """Detected self-referential inference loop."""
    ts_ns: int
    source: str
    loop_depth: int                 # how many hops back before external grounding
    self_referential: bool
    severity: CognitiveSeverity
    evidence: tuple[str, ...] = ()
    detail: str = ""


@dataclass(frozen=True, slots=True)
class EpistemicDriftReport:
    """Rolling divergence between predicted and observed outcomes."""
    ts_ns: int
    window_ns: int
    drift_score: float              # 0.0 = calibrated … 1.0 = complete divergence
    mean_absolute_error: float
    accumulated_error: float
    n_samples: int
    threshold_breached: bool = False
    severity: CognitiveSeverity = CognitiveSeverity.INFO
    detail: str = ""


@dataclass(frozen=True, slots=True)
class LearningTruthfulnessReport:
    """Ratio of externally-grounded to synthetic learning signals."""
    ts_ns: int
    window_n: int
    external_ratio: float           # 1.0 = fully grounded, 0.0 = fully synthetic
    synthetic_count: int
    grounded_count: int
    passed: bool
    severity: CognitiveSeverity = CognitiveSeverity.INFO
    detail: str = ""


@dataclass(frozen=True, slots=True)
class LineageValidationResult:
    """Strategy lineage chain integrity check."""
    ts_ns: int
    strategy_id: str
    chain_depth: int
    passed: bool
    violations: tuple[CognitiveViolationKind, ...] = ()
    detail: str = ""


@dataclass(frozen=True, slots=True)
class IdentityStabilityReport:
    """Archetype / behavioral fingerprint drift measurement."""
    ts_ns: int
    trader_id: str
    similarity_score: float         # cosine sim vs. 7d baseline; 1.0 = identical
    drift_magnitude: float          # 1 - similarity_score
    passed: bool
    severity: CognitiveSeverity = CognitiveSeverity.INFO
    detail: str = ""


@dataclass(frozen=True, slots=True)
class SyntheticFeedbackReport:
    """Detection of paper/simulated signals polluting live learning."""
    ts_ns: int
    source: str
    mode: str                       # "paper" | "live" | "unknown"
    is_synthetic: bool
    severity: CognitiveSeverity = CognitiveSeverity.INFO
    detail: str = ""


@dataclass(frozen=True, slots=True)
class RewardHackingReport:
    """Reward-function gaming detection."""
    ts_ns: int
    strategy_id: str
    reward_trend: float             # positive = increasing reward
    objective_trend: float          # positive = improving true objective
    correlation: float              # reward–objective correlation; low = hacking
    hacking_detected: bool
    severity: CognitiveSeverity = CognitiveSeverity.INFO
    detail: str = ""


@dataclass(frozen=True, slots=True)
class CausalConsistencyReport:
    """Attribution chain causal-consistency check."""
    ts_ns: int
    decision_id: str
    passed: bool
    violations: tuple[CognitiveViolationKind, ...] = ()
    detail: str = ""


@dataclass(frozen=True, slots=True)
class CognitiveIntegrityStatus:
    """Aggregate snapshot of all cognitive-governance guards."""
    ts_ns: int
    overall_healthy: bool
    belief_integrity_ok: bool
    memory_clean: bool
    mutation_safe: bool
    no_hallucination: bool
    epistemic_current: bool
    learning_truthful: bool
    lineage_intact: bool
    identity_stable: bool
    no_synthetic_feedback: bool
    no_reward_hacking: bool
    causal_consistent: bool
    active_violations: tuple[CognitiveViolationKind, ...] = ()
    detail: str = ""


__all__ = [
    "CognitiveViolationKind",
    "CognitiveSeverity",
    "BeliefIntegrityReport",
    "MemoryContaminationReport",
    "MutationValidationResult",
    "HallucinationReport",
    "EpistemicDriftReport",
    "LearningTruthfulnessReport",
    "LineageValidationResult",
    "IdentityStabilityReport",
    "SyntheticFeedbackReport",
    "RewardHackingReport",
    "CausalConsistencyReport",
    "CognitiveIntegrityStatus",
]

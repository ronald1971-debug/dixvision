"""
core/contracts/cognitive_observability.py
DIX VISION v42.2 — Cognitive Observability Protocol Contracts

Typed contracts for the two primary intelligences' observable thought processes:

  INDIRA events  → ledger stream  INTELLIGENCE/COGNITION
  DYON events    → ledger stream  SYSTEM/DYON

All event types are frozen, slotted dataclasses (INV-08). They carry only
primitive and tuple fields to preserve INV-15 replay determinism. No IO,
no wall-clock access, no PRNG — callers must supply ts_ns.

Projection surfaces (dashboards, operator UIs) consume these contracts
via CognitiveObservabilityProjection — the typed envelope that all
cognitive event types are serialised into for transport.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


# ---------------------------------------------------------------------------
# Ledger stream identifiers
# ---------------------------------------------------------------------------

INDIRA_COGNITION_STREAM: str = "INTELLIGENCE/COGNITION"
DYON_SYSTEM_STREAM: str = "SYSTEM/DYON"


# ---------------------------------------------------------------------------
# Taxonomy enumerations
# ---------------------------------------------------------------------------

class CognitiveIntelligence(StrEnum):
    """Which primary intelligence produced this cognitive event."""
    INDIRA = "INDIRA"
    DYON = "DYON"


class CognitiveEventKind(StrEnum):
    """All cognitive observability event types across both intelligences."""
    # --- INDIRA ---
    THOUGHT_STREAM       = "THOUGHT_STREAM"        # live reasoning trace
    BELIEF_EVOLUTION     = "BELIEF_EVOLUTION"      # belief value shifts
    MEMORY_FORMATION     = "MEMORY_FORMATION"      # new/updated memory entry
    MUTATION_TRACE       = "MUTATION_TRACE"        # strategy parameter mutation
    CONFIDENCE_SHIFT     = "CONFIDENCE_SHIFT"      # confidence delta events
    ARCHETYPE_EVOLUTION  = "ARCHETYPE_EVOLUTION"   # trader archetype fitness change
    CAUSAL_CHAIN         = "CAUSAL_CHAIN"          # causal reasoning chain formed
    RESEARCH_DISCOVERY   = "RESEARCH_DISCOVERY"    # autonomous research finding
    # --- DYON ---
    PATCH_PROPOSAL       = "PATCH_PROPOSAL"        # DYON proposes a system patch
    TOPOLOGY_DRIFT       = "TOPOLOGY_DRIFT"        # module topology deviates from spec
    ARCHITECTURAL_DRIFT  = "ARCHITECTURAL_DRIFT"   # invariant/contract violation detected
    REPAIR_PIPELINE      = "REPAIR_PIPELINE"       # autonomous repair pipeline activity
    DEPENDENCY_ANOMALY   = "DEPENDENCY_ANOMALY"    # import graph anomaly
    RUNTIME_ANOMALY      = "RUNTIME_ANOMALY"       # runtime failure / unexpected state


class MemoryKind(StrEnum):
    EPISODIC   = "episodic"
    SEMANTIC   = "semantic"
    PROCEDURAL = "procedural"
    STRATEGY   = "strategy"
    REGRET     = "regret"
    MUTATION_LINEAGE = "mutation_lineage"
    BEHAVIORAL = "behavioral"
    SIMULATION = "simulation"
    ARCHITECTURAL = "architectural"
    GOVERNANCE = "governance"


class GovernanceStatus(StrEnum):
    PROPOSED   = "PROPOSED"
    SIMULATED  = "SIMULATED"
    APPROVED   = "APPROVED"
    REJECTED   = "REJECTED"
    DEPLOYED   = "DEPLOYED"
    ROLLED_BACK = "ROLLED_BACK"


class DriftSeverity(StrEnum):
    INFO     = "INFO"
    WARNING  = "WARNING"
    CRITICAL = "CRITICAL"


class RepairStage(StrEnum):
    DIAGNOSIS         = "DIAGNOSIS"
    PATCH_GENERATION  = "PATCH_GENERATION"
    SIMULATION        = "SIMULATION"
    VALIDATION        = "VALIDATION"
    DEPLOYMENT        = "DEPLOYMENT"
    ROLLBACK          = "ROLLBACK"


class RepairOutcome(StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS     = "SUCCESS"
    FAILED      = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class PatchKind(StrEnum):
    REFACTOR      = "REFACTOR"
    FIX           = "FIX"
    OPTIMIZATION  = "OPTIMIZATION"
    ARCHITECTURAL = "ARCHITECTURAL"
    DEPENDENCY    = "DEPENDENCY"


class DependencyAnomalyKind(StrEnum):
    CIRCULAR         = "CIRCULAR"
    MISSING          = "MISSING"
    FORBIDDEN        = "FORBIDDEN"
    VERSION_CONFLICT = "VERSION_CONFLICT"


# ---------------------------------------------------------------------------
# INDIRA cognitive observability events
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ThoughtStreamEvent:
    """A single step in INDIRA's live reasoning trace."""
    ts_ns: int
    thought_id: str
    reasoning_step: str       # e.g. "signal_processing", "regime_detection", "intent_formation"
    context: str              # human-readable description of what INDIRA is reasoning about
    confidence: float
    inputs: tuple[str, ...]   # IDs of contributing signals, beliefs, or prior thoughts
    conclusion: str
    intelligence: CognitiveIntelligence = CognitiveIntelligence.INDIRA
    stream: str = INDIRA_COGNITION_STREAM


@dataclass(frozen=True, slots=True)
class BeliefEvolutionEvent:
    """INDIRA's belief about a subject has shifted."""
    ts_ns: int
    belief_id: str
    subject: str              # what the belief is about (e.g. "BTC_regime", "ETH_momentum")
    old_value: float | None   # None if this is the first formation
    new_value: float
    delta: float
    driver: str               # what caused the shift (signal ID, research finding, regime change)
    confidence: float
    intelligence: CognitiveIntelligence = CognitiveIntelligence.INDIRA
    stream: str = INDIRA_COGNITION_STREAM


@dataclass(frozen=True, slots=True)
class MemoryFormationEvent:
    """INDIRA has created or updated a memory entry."""
    ts_ns: int
    memory_id: str
    memory_kind: MemoryKind
    subject: str
    content_summary: str
    source: str               # "simulation" | "research" | "live_signal" | "governance_event"
    confidence: float
    replaces_memory_id: str | None  # set when updating an existing memory
    intelligence: CognitiveIntelligence = CognitiveIntelligence.INDIRA
    stream: str = INDIRA_COGNITION_STREAM


@dataclass(frozen=True, slots=True)
class MutationTraceEvent:
    """A strategy or parameter mutation has been proposed or actioned."""
    ts_ns: int
    mutation_id: str
    target: str               # module.parameter path being mutated
    old_value: str            # serialised representation
    new_value: str            # serialised representation
    rationale: str
    proposer: str             # module path that proposed the mutation
    governance_status: GovernanceStatus
    lineage_parent_id: str | None   # ID of the mutation this was derived from
    intelligence: CognitiveIntelligence = CognitiveIntelligence.INDIRA
    stream: str = INDIRA_COGNITION_STREAM


@dataclass(frozen=True, slots=True)
class ConfidenceShiftEvent:
    """INDIRA's confidence in a subject has changed materially."""
    ts_ns: int
    subject: str
    old_confidence: float
    new_confidence: float
    delta: float
    driver: str               # signal, regime transition, belief update, etc.
    intelligence: CognitiveIntelligence = CognitiveIntelligence.INDIRA
    stream: str = INDIRA_COGNITION_STREAM


@dataclass(frozen=True, slots=True)
class ArchetypeEvolutionEvent:
    """A trader archetype's fitness score has been updated."""
    ts_ns: int
    archetype_id: str
    archetype_name: str
    old_fitness: float | None   # None if first evaluation
    new_fitness: float
    delta: float
    regime: str
    evaluation_basis: str     # e.g. "backtest", "simulation", "live_paper"
    intelligence: CognitiveIntelligence = CognitiveIntelligence.INDIRA
    stream: str = INDIRA_COGNITION_STREAM


@dataclass(frozen=True, slots=True)
class CausalChainEvent:
    """INDIRA has formed or updated a causal reasoning chain."""
    ts_ns: int
    chain_id: str
    hypothesis: str
    causes: tuple[str, ...]
    effects: tuple[str, ...]
    confidence: float
    evidence_count: int
    intelligence: CognitiveIntelligence = CognitiveIntelligence.INDIRA
    stream: str = INDIRA_COGNITION_STREAM


@dataclass(frozen=True, slots=True)
class ResearchDiscoveryEvent:
    """INDIRA's autonomous research has produced a new finding."""
    ts_ns: int
    discovery_id: str
    source_url: str
    topic: str
    summary: str
    confidence: float
    connected_to: tuple[str, ...]  # memory/belief/chain IDs this connects to
    trust_score: float             # source credibility [0.0, 1.0]
    intelligence: CognitiveIntelligence = CognitiveIntelligence.INDIRA
    stream: str = INDIRA_COGNITION_STREAM


# ---------------------------------------------------------------------------
# DYON engineering observability events
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PatchProposalEvent:
    """DYON has proposed a system patch or architectural change."""
    ts_ns: int
    proposal_id: str
    target_module: str
    patch_kind: PatchKind
    description: str
    rationale: str
    risk_level: str            # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    governance_status: GovernanceStatus
    simulation_outcome: str | None   # summary of sandbox simulation result
    intelligence: CognitiveIntelligence = CognitiveIntelligence.DYON
    stream: str = DYON_SYSTEM_STREAM


@dataclass(frozen=True, slots=True)
class TopologyDriftEvent:
    """DYON has detected a module's topology deviating from its declared spec."""
    ts_ns: int
    drift_id: str
    module: str
    expected_topology: str
    actual_topology: str
    drift_severity: DriftSeverity
    description: str
    recommended_action: str | None
    intelligence: CognitiveIntelligence = CognitiveIntelligence.DYON
    stream: str = DYON_SYSTEM_STREAM


@dataclass(frozen=True, slots=True)
class ArchitecturalDriftEvent:
    """DYON has detected a violation of a declared architectural invariant."""
    ts_ns: int
    drift_id: str
    invariant_id: str          # e.g. "INV-15", "INV-08", "B1"
    violation_description: str
    severity: DriftSeverity
    affected_modules: tuple[str, ...]
    recommended_action: str | None
    intelligence: CognitiveIntelligence = CognitiveIntelligence.DYON
    stream: str = DYON_SYSTEM_STREAM


@dataclass(frozen=True, slots=True)
class RepairPipelineEvent:
    """DYON's autonomous repair pipeline has advanced to a new stage."""
    ts_ns: int
    pipeline_id: str
    stage: RepairStage
    target: str
    description: str
    outcome: RepairOutcome
    patch_proposal_id: str | None   # links to PatchProposalEvent
    intelligence: CognitiveIntelligence = CognitiveIntelligence.DYON
    stream: str = DYON_SYSTEM_STREAM


@dataclass(frozen=True, slots=True)
class DependencyAnomalyEvent:
    """DYON has detected an anomaly in the module dependency graph."""
    ts_ns: int
    anomaly_id: str
    source_module: str
    target_module: str
    anomaly_kind: DependencyAnomalyKind
    severity: DriftSeverity
    description: str
    intelligence: CognitiveIntelligence = CognitiveIntelligence.DYON
    stream: str = DYON_SYSTEM_STREAM


@dataclass(frozen=True, slots=True)
class RuntimeAnomalyEvent:
    """DYON has detected an unexpected runtime state or subsystem failure."""
    ts_ns: int
    anomaly_id: str
    subsystem: str
    anomaly_kind: str
    severity: str               # "INFO" | "WARNING" | "CRITICAL" | "FATAL"
    description: str
    auto_repair_triggered: bool
    intelligence: CognitiveIntelligence = CognitiveIntelligence.DYON
    stream: str = DYON_SYSTEM_STREAM


# ---------------------------------------------------------------------------
# Projection envelope — consumed by operator dashboard surfaces
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class CognitiveObservabilityProjection:
    """
    Typed projection envelope for operator-facing cognitive observability surfaces.

    All cognitive event types are serialised into this envelope by the
    projection engine before being delivered to dashboard projection surfaces.
    The detail dict is a shallow snapshot — suitable for JSON serialisation
    to WebSocket / SSE streams.
    """
    ts_ns: int
    intelligence: CognitiveIntelligence
    event_kind: CognitiveEventKind
    event_id: str             # thought_id / belief_id / mutation_id / proposal_id / etc.
    headline: str             # human-readable one-liner for the operator UI
    confidence: float | None  # None for events that don't carry confidence
    stream: str               # ledger stream (INDIRA_COGNITION_STREAM or DYON_SYSTEM_STREAM)
    detail: tuple[tuple[str, str], ...]  # (key, value) pairs; fully immutable (INV-08)


# ---------------------------------------------------------------------------
# Union type for exhaustive pattern matching in projection engine
# ---------------------------------------------------------------------------

AnyIndiraEvent = (
    ThoughtStreamEvent
    | BeliefEvolutionEvent
    | MemoryFormationEvent
    | MutationTraceEvent
    | ConfidenceShiftEvent
    | ArchetypeEvolutionEvent
    | CausalChainEvent
    | ResearchDiscoveryEvent
)

AnyDyonEvent = (
    PatchProposalEvent
    | TopologyDriftEvent
    | ArchitecturalDriftEvent
    | RepairPipelineEvent
    | DependencyAnomalyEvent
    | RuntimeAnomalyEvent
)

AnyCognitiveEvent = AnyIndiraEvent | AnyDyonEvent


__all__ = [
    # Stream constants
    "INDIRA_COGNITION_STREAM",
    "DYON_SYSTEM_STREAM",
    # Enums
    "CognitiveIntelligence",
    "CognitiveEventKind",
    "MemoryKind",
    "GovernanceStatus",
    "DriftSeverity",
    "RepairStage",
    "RepairOutcome",
    "PatchKind",
    "DependencyAnomalyKind",
    # INDIRA events
    "ThoughtStreamEvent",
    "BeliefEvolutionEvent",
    "MemoryFormationEvent",
    "MutationTraceEvent",
    "ConfidenceShiftEvent",
    "ArchetypeEvolutionEvent",
    "CausalChainEvent",
    "ResearchDiscoveryEvent",
    # DYON events
    "PatchProposalEvent",
    "TopologyDriftEvent",
    "ArchitecturalDriftEvent",
    "RepairPipelineEvent",
    "DependencyAnomalyEvent",
    "RuntimeAnomalyEvent",
    # Projection envelope
    "CognitiveObservabilityProjection",
    # Union types
    "AnyIndiraEvent",
    "AnyDyonEvent",
    "AnyCognitiveEvent",
]

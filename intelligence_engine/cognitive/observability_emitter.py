"""
intelligence_engine/cognitive/observability_emitter.py
DIX VISION v42.2 — INDIRA Cognitive Observability Emitter

Best-effort emission of cognitive observability events to the ledger.
All public functions are fire-and-forget: they catch every exception
internally and never raise — cognitive observability must not disrupt
the hot path.

Event mapping:
  event_type = "INTELLIGENCE"
  sub_type   = CognitiveEventKind value (e.g. "THOUGHT_STREAM")
  source     = "INDIRA"

B1/B24: This module may import core.contracts and state.ledger only.
It must NOT import governance_engine or execution_engine internals.
INV-15: Emit calls are side-effects that occur AFTER compute; they
do not alter the deterministic compute path.
"""

from __future__ import annotations

import uuid as _uuid
from typing import Any

from core.contracts.cognitive_observability import (
    INDIRA_COGNITION_STREAM,
    ArchetypeEvolutionEvent,
    BeliefEvolutionEvent,
    CausalChainEvent,
    CognitiveEventKind,
    ConfidenceShiftEvent,
    MemoryFormationEvent,
    MutationTraceEvent,
    ResearchDiscoveryEvent,
    ThoughtStreamEvent,
)

_INTELLIGENCE_EVENT_TYPE = "INTELLIGENCE"
_INDIRA_SOURCE = "INDIRA"

# Minimum absolute confidence delta before a ConfidenceShiftEvent is emitted.
CONFIDENCE_SHIFT_THRESHOLD: float = 0.04


def _append(sub_type: str, payload: dict[str, Any]) -> None:
    """Best-effort ledger append — never raises."""
    try:
        from state.ledger.event_store import append_event
        append_event(_INTELLIGENCE_EVENT_TYPE, sub_type, _INDIRA_SOURCE, payload)
    except Exception:  # pragma: no cover
        pass


# ---------------------------------------------------------------------------
# INDIRA cognitive event emitters
# ---------------------------------------------------------------------------

def emit_thought_stream(
    *,
    ts_ns: int,
    reasoning_step: str,
    context: str,
    confidence: float,
    inputs: tuple[str, ...],
    conclusion: str,
    thought_id: str | None = None,
) -> str:
    """Emit a ThoughtStreamEvent and return its thought_id."""
    tid = thought_id or str(_uuid.uuid4())
    event = ThoughtStreamEvent(
        ts_ns=ts_ns,
        thought_id=tid,
        reasoning_step=reasoning_step,
        context=context,
        confidence=confidence,
        inputs=inputs,
        conclusion=conclusion,
    )
    _append(
        CognitiveEventKind.THOUGHT_STREAM,
        {
            "thought_id": event.thought_id,
            "reasoning_step": event.reasoning_step,
            "context": event.context,
            "confidence": event.confidence,
            "inputs": list(event.inputs),
            "conclusion": event.conclusion,
            "stream": INDIRA_COGNITION_STREAM,
        },
    )
    return tid


def emit_confidence_shift(
    *,
    ts_ns: int,
    subject: str,
    old_confidence: float,
    new_confidence: float,
    driver: str,
) -> None:
    """Emit a ConfidenceShiftEvent if delta exceeds CONFIDENCE_SHIFT_THRESHOLD."""
    delta = new_confidence - old_confidence
    if abs(delta) < CONFIDENCE_SHIFT_THRESHOLD:
        return
    event = ConfidenceShiftEvent(
        ts_ns=ts_ns,
        subject=subject,
        old_confidence=old_confidence,
        new_confidence=new_confidence,
        delta=delta,
        driver=driver,
    )
    _append(
        CognitiveEventKind.CONFIDENCE_SHIFT,
        {
            "subject": event.subject,
            "old_confidence": event.old_confidence,
            "new_confidence": event.new_confidence,
            "delta": event.delta,
            "driver": event.driver,
            "stream": INDIRA_COGNITION_STREAM,
        },
    )


def emit_belief_evolution(
    *,
    ts_ns: int,
    belief_id: str,
    subject: str,
    old_value: float | None,
    new_value: float,
    driver: str,
    confidence: float,
) -> None:
    """Emit a BeliefEvolutionEvent."""
    delta = new_value - (old_value if old_value is not None else new_value)
    event = BeliefEvolutionEvent(
        ts_ns=ts_ns,
        belief_id=belief_id,
        subject=subject,
        old_value=old_value,
        new_value=new_value,
        delta=delta,
        driver=driver,
        confidence=confidence,
    )
    _append(
        CognitiveEventKind.BELIEF_EVOLUTION,
        {
            "belief_id": event.belief_id,
            "subject": event.subject,
            "old_value": event.old_value,
            "new_value": event.new_value,
            "delta": event.delta,
            "driver": event.driver,
            "confidence": event.confidence,
            "stream": INDIRA_COGNITION_STREAM,
        },
    )


def emit_memory_formation(
    *,
    ts_ns: int,
    memory_kind: str,
    subject: str,
    content_summary: str,
    source: str,
    confidence: float,
    replaces_memory_id: str | None = None,
    memory_id: str | None = None,
) -> str:
    """Emit a MemoryFormationEvent and return its memory_id."""
    from core.contracts.cognitive_observability import MemoryKind
    mid = memory_id or str(_uuid.uuid4())
    try:
        kind = MemoryKind(memory_kind)
    except ValueError:
        kind = MemoryKind.SEMANTIC
    event = MemoryFormationEvent(
        ts_ns=ts_ns,
        memory_id=mid,
        memory_kind=kind,
        subject=subject,
        content_summary=content_summary,
        source=source,
        confidence=confidence,
        replaces_memory_id=replaces_memory_id,
    )
    _append(
        CognitiveEventKind.MEMORY_FORMATION,
        {
            "memory_id": event.memory_id,
            "memory_kind": event.memory_kind.value,
            "subject": event.subject,
            "content_summary": event.content_summary,
            "source": event.source,
            "confidence": event.confidence,
            "replaces_memory_id": event.replaces_memory_id,
            "stream": INDIRA_COGNITION_STREAM,
        },
    )
    return mid


def emit_mutation_trace(
    *,
    ts_ns: int,
    mutation_id: str,
    target: str,
    old_value: str,
    new_value: str,
    rationale: str,
    proposer: str,
    governance_status: str,
    lineage_parent_id: str | None = None,
) -> None:
    """Emit a MutationTraceEvent."""
    from core.contracts.cognitive_observability import GovernanceStatus
    try:
        status = GovernanceStatus(governance_status)
    except ValueError:
        status = GovernanceStatus.PROPOSED
    event = MutationTraceEvent(
        ts_ns=ts_ns,
        mutation_id=mutation_id,
        target=target,
        old_value=old_value,
        new_value=new_value,
        rationale=rationale,
        proposer=proposer,
        governance_status=status,
        lineage_parent_id=lineage_parent_id,
    )
    _append(
        CognitiveEventKind.MUTATION_TRACE,
        {
            "mutation_id": event.mutation_id,
            "target": event.target,
            "old_value": event.old_value,
            "new_value": event.new_value,
            "rationale": event.rationale,
            "proposer": event.proposer,
            "governance_status": event.governance_status.value,
            "lineage_parent_id": event.lineage_parent_id,
            "stream": INDIRA_COGNITION_STREAM,
        },
    )


def emit_archetype_evolution(
    *,
    ts_ns: int,
    archetype_id: str,
    archetype_name: str,
    old_fitness: float | None,
    new_fitness: float,
    regime: str,
    evaluation_basis: str,
) -> None:
    """Emit an ArchetypeEvolutionEvent."""
    delta = new_fitness - (old_fitness if old_fitness is not None else new_fitness)
    event = ArchetypeEvolutionEvent(
        ts_ns=ts_ns,
        archetype_id=archetype_id,
        archetype_name=archetype_name,
        old_fitness=old_fitness,
        new_fitness=new_fitness,
        delta=delta,
        regime=regime,
        evaluation_basis=evaluation_basis,
    )
    _append(
        CognitiveEventKind.ARCHETYPE_EVOLUTION,
        {
            "archetype_id": event.archetype_id,
            "archetype_name": event.archetype_name,
            "old_fitness": event.old_fitness,
            "new_fitness": event.new_fitness,
            "delta": event.delta,
            "regime": event.regime,
            "evaluation_basis": event.evaluation_basis,
            "stream": INDIRA_COGNITION_STREAM,
        },
    )


def emit_causal_chain(
    *,
    ts_ns: int,
    hypothesis: str,
    causes: tuple[str, ...],
    effects: tuple[str, ...],
    confidence: float,
    evidence_count: int,
    chain_id: str | None = None,
) -> str:
    """Emit a CausalChainEvent and return its chain_id."""
    cid = chain_id or str(_uuid.uuid4())
    event = CausalChainEvent(
        ts_ns=ts_ns,
        chain_id=cid,
        hypothesis=hypothesis,
        causes=causes,
        effects=effects,
        confidence=confidence,
        evidence_count=evidence_count,
    )
    _append(
        CognitiveEventKind.CAUSAL_CHAIN,
        {
            "chain_id": event.chain_id,
            "hypothesis": event.hypothesis,
            "causes": list(event.causes),
            "effects": list(event.effects),
            "confidence": event.confidence,
            "evidence_count": event.evidence_count,
            "stream": INDIRA_COGNITION_STREAM,
        },
    )
    return cid


def emit_research_discovery(
    *,
    ts_ns: int,
    source_url: str,
    topic: str,
    summary: str,
    confidence: float,
    connected_to: tuple[str, ...] = (),
    trust_score: float = 0.5,
    discovery_id: str | None = None,
) -> str:
    """Emit a ResearchDiscoveryEvent and return its discovery_id."""
    did = discovery_id or str(_uuid.uuid4())
    event = ResearchDiscoveryEvent(
        ts_ns=ts_ns,
        discovery_id=did,
        source_url=source_url,
        topic=topic,
        summary=summary,
        confidence=confidence,
        connected_to=connected_to,
        trust_score=trust_score,
    )
    _append(
        CognitiveEventKind.RESEARCH_DISCOVERY,
        {
            "discovery_id": event.discovery_id,
            "source_url": event.source_url,
            "topic": event.topic,
            "summary": event.summary,
            "confidence": event.confidence,
            "connected_to": list(event.connected_to),
            "trust_score": event.trust_score,
            "stream": INDIRA_COGNITION_STREAM,
        },
    )
    return did


__all__ = [
    "CONFIDENCE_SHIFT_THRESHOLD",
    "emit_archetype_evolution",
    "emit_belief_evolution",
    "emit_causal_chain",
    "emit_confidence_shift",
    "emit_memory_formation",
    "emit_mutation_trace",
    "emit_research_discovery",
    "emit_thought_stream",
]

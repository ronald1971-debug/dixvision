"""
evolution_engine/charter/dyon_observability_emitter.py
DIX VISION v42.2 — DYON Engineering Observability Emitter

Best-effort emission of DYON cognitive observability events to the ledger.
All public functions are fire-and-forget: they catch every exception
internally and never raise — observability must not disrupt the evolution
pipeline.

Event mapping:
  event_type = "SYSTEM"
  sub_type   = CognitiveEventKind value (e.g. "PATCH_PROPOSAL")
  source     = "DYON"

B1: This module may import core.contracts and state.ledger only.
It must NOT import INDIRA-only market adapter modules.
INV-15: Emit calls occur AFTER compute; they do not alter the
deterministic compute path.
"""

from __future__ import annotations

import uuid as _uuid
from typing import Any

from core.contracts.cognitive_observability import (
    DYON_SYSTEM_STREAM,
    ArchitecturalDriftEvent,
    CognitiveEventKind,
    DependencyAnomalyEvent,
    DependencyAnomalyKind,
    DriftSeverity,
    GovernanceStatus,
    PatchKind,
    PatchProposalEvent,
    RepairOutcome,
    RepairPipelineEvent,
    RepairStage,
    RuntimeAnomalyEvent,
    TopologyDriftEvent,
)

_SYSTEM_EVENT_TYPE = "SYSTEM"
_DYON_SOURCE = "DYON"


def _append(sub_type: str, payload: dict[str, Any]) -> None:
    """Best-effort ledger append — never raises."""
    try:
        from state.ledger.event_store import append_event
        append_event(_SYSTEM_EVENT_TYPE, sub_type, _DYON_SOURCE, payload)
    except Exception:  # pragma: no cover
        pass


# ---------------------------------------------------------------------------
# DYON engineering observability emitters
# ---------------------------------------------------------------------------

def emit_patch_proposal(
    *,
    ts_ns: int,
    proposal_id: str,
    target_module: str,
    patch_kind: str,
    description: str,
    rationale: str,
    risk_level: str = "LOW",
    governance_status: str = "PROPOSED",
    simulation_outcome: str | None = None,
) -> None:
    """Emit a PatchProposalEvent to the DYON observability stream."""
    try:
        kind = PatchKind(patch_kind)
    except ValueError:
        kind = PatchKind.REFACTOR
    try:
        status = GovernanceStatus(governance_status)
    except ValueError:
        status = GovernanceStatus.PROPOSED
    event = PatchProposalEvent(
        ts_ns=ts_ns,
        proposal_id=proposal_id,
        target_module=target_module,
        patch_kind=kind,
        description=description,
        rationale=rationale,
        risk_level=risk_level,
        governance_status=status,
        simulation_outcome=simulation_outcome,
    )
    _append(
        CognitiveEventKind.PATCH_PROPOSAL,
        {
            "proposal_id": event.proposal_id,
            "target_module": event.target_module,
            "patch_kind": event.patch_kind.value,
            "description": event.description,
            "rationale": event.rationale,
            "risk_level": event.risk_level,
            "governance_status": event.governance_status.value,
            "simulation_outcome": event.simulation_outcome,
            "stream": DYON_SYSTEM_STREAM,
        },
    )


def emit_topology_drift(
    *,
    ts_ns: int,
    module: str,
    expected_topology: str,
    actual_topology: str,
    drift_severity: str,
    description: str,
    recommended_action: str | None = None,
    drift_id: str | None = None,
) -> str:
    """Emit a TopologyDriftEvent and return its drift_id."""
    did = drift_id or str(_uuid.uuid4())
    try:
        severity = DriftSeverity(drift_severity)
    except ValueError:
        severity = DriftSeverity.WARNING
    event = TopologyDriftEvent(
        ts_ns=ts_ns,
        drift_id=did,
        module=module,
        expected_topology=expected_topology,
        actual_topology=actual_topology,
        drift_severity=severity,
        description=description,
        recommended_action=recommended_action,
    )
    _append(
        CognitiveEventKind.TOPOLOGY_DRIFT,
        {
            "drift_id": event.drift_id,
            "module": event.module,
            "expected_topology": event.expected_topology,
            "actual_topology": event.actual_topology,
            "drift_severity": event.drift_severity.value,
            "description": event.description,
            "recommended_action": event.recommended_action,
            "stream": DYON_SYSTEM_STREAM,
        },
    )
    return did


def emit_architectural_drift(
    *,
    ts_ns: int,
    invariant_id: str,
    violation_description: str,
    severity: str,
    affected_modules: tuple[str, ...],
    recommended_action: str | None = None,
    drift_id: str | None = None,
) -> str:
    """Emit an ArchitecturalDriftEvent and return its drift_id."""
    did = drift_id or str(_uuid.uuid4())
    try:
        sev = DriftSeverity(severity)
    except ValueError:
        sev = DriftSeverity.WARNING
    event = ArchitecturalDriftEvent(
        ts_ns=ts_ns,
        drift_id=did,
        invariant_id=invariant_id,
        violation_description=violation_description,
        severity=sev,
        affected_modules=affected_modules,
        recommended_action=recommended_action,
    )
    _append(
        CognitiveEventKind.ARCHITECTURAL_DRIFT,
        {
            "drift_id": event.drift_id,
            "invariant_id": event.invariant_id,
            "violation_description": event.violation_description,
            "severity": event.severity.value,
            "affected_modules": list(event.affected_modules),
            "recommended_action": event.recommended_action,
            "stream": DYON_SYSTEM_STREAM,
        },
    )
    return did


def emit_repair_pipeline(
    *,
    ts_ns: int,
    pipeline_id: str,
    stage: str,
    target: str,
    description: str,
    outcome: str,
    patch_proposal_id: str | None = None,
) -> None:
    """Emit a RepairPipelineEvent."""
    try:
        stg = RepairStage(stage)
    except ValueError:
        stg = RepairStage.DIAGNOSIS
    try:
        out = RepairOutcome(outcome)
    except ValueError:
        out = RepairOutcome.IN_PROGRESS
    event = RepairPipelineEvent(
        ts_ns=ts_ns,
        pipeline_id=pipeline_id,
        stage=stg,
        target=target,
        description=description,
        outcome=out,
        patch_proposal_id=patch_proposal_id,
    )
    _append(
        CognitiveEventKind.REPAIR_PIPELINE,
        {
            "pipeline_id": event.pipeline_id,
            "stage": event.stage.value,
            "target": event.target,
            "description": event.description,
            "outcome": event.outcome.value,
            "patch_proposal_id": event.patch_proposal_id,
            "stream": DYON_SYSTEM_STREAM,
        },
    )


def emit_dependency_anomaly(
    *,
    ts_ns: int,
    source_module: str,
    target_module: str,
    anomaly_kind: str,
    severity: str,
    description: str,
    anomaly_id: str | None = None,
) -> str:
    """Emit a DependencyAnomalyEvent and return its anomaly_id."""
    aid = anomaly_id or str(_uuid.uuid4())
    try:
        kind = DependencyAnomalyKind(anomaly_kind)
    except ValueError:
        kind = DependencyAnomalyKind.FORBIDDEN
    try:
        sev = DriftSeverity(severity)
    except ValueError:
        sev = DriftSeverity.WARNING
    event = DependencyAnomalyEvent(
        ts_ns=ts_ns,
        anomaly_id=aid,
        source_module=source_module,
        target_module=target_module,
        anomaly_kind=kind,
        severity=sev,
        description=description,
    )
    _append(
        CognitiveEventKind.DEPENDENCY_ANOMALY,
        {
            "anomaly_id": event.anomaly_id,
            "source_module": event.source_module,
            "target_module": event.target_module,
            "anomaly_kind": event.anomaly_kind.value,
            "severity": event.severity.value,
            "description": event.description,
            "stream": DYON_SYSTEM_STREAM,
        },
    )
    return aid


def emit_runtime_anomaly(
    *,
    ts_ns: int,
    subsystem: str,
    anomaly_kind: str,
    severity: str,
    description: str,
    auto_repair_triggered: bool = False,
    anomaly_id: str | None = None,
) -> str:
    """Emit a RuntimeAnomalyEvent and return its anomaly_id."""
    aid = anomaly_id or str(_uuid.uuid4())
    event = RuntimeAnomalyEvent(
        ts_ns=ts_ns,
        anomaly_id=aid,
        subsystem=subsystem,
        anomaly_kind=anomaly_kind,
        severity=severity,
        description=description,
        auto_repair_triggered=auto_repair_triggered,
    )
    _append(
        CognitiveEventKind.RUNTIME_ANOMALY,
        {
            "anomaly_id": event.anomaly_id,
            "subsystem": event.subsystem,
            "anomaly_kind": event.anomaly_kind,
            "severity": event.severity,
            "description": event.description,
            "auto_repair_triggered": event.auto_repair_triggered,
            "stream": DYON_SYSTEM_STREAM,
        },
    )
    return aid


__all__ = [
    "emit_architectural_drift",
    "emit_dependency_anomaly",
    "emit_patch_proposal",
    "emit_repair_pipeline",
    "emit_runtime_anomaly",
    "emit_topology_drift",
]

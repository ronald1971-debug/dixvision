"""
core/contracts/system_governance.py
DIX VISION v42.2 — System Governance contract types.

System governance protects the runtime structural integrity of DIX VISION.
Without it the intelligence fragments into unstable subsystems that drift
away from each other and become impossible to reason about or replay.

Protections formalised here:
  1. Contract Integrity     — inter-subsystem contracts are honoured at runtime
  2. Topology Guard         — no illegal cross-domain imports (B1 constraint)
  3. Runtime Consistency    — shared state remains consistent across subsystems
  4. Replay Integrity       — events are deterministically replayable (INV-15)
  5. Convergence Monitor    — subsystems are wiring up, not drifting apart
  6. Dependency Validator   — declared dependencies match runtime reality
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ContractViolationKind(StrEnum):
    INTERFACE_MISMATCH      = "INTERFACE_MISMATCH"    # expected API not present
    NULL_CONTRACT           = "NULL_CONTRACT"          # subsystem registered no contract
    VERSION_MISMATCH        = "VERSION_MISMATCH"       # incompatible schema versions
    TIMEOUT_VIOLATION       = "TIMEOUT_VIOLATION"      # contract SLA breached
    MISSING_LEDGER_EMIT     = "MISSING_LEDGER_EMIT"    # subsystem not emitting audit events


class TopologyViolationKind(StrEnum):
    B1_CROSS_ENGINE_IMPORT   = "B1_CROSS_ENGINE_IMPORT"   # direct cross-engine import
    DOMAIN_BOUNDARY_BREACH   = "DOMAIN_BOUNDARY_BREACH"   # execution↔system boundary
    UNDECLARED_DEPENDENCY    = "UNDECLARED_DEPENDENCY"     # runtime import not declared
    CIRCULAR_IMPORT          = "CIRCULAR_IMPORT"           # import cycle detected


class ConvergenceState(StrEnum):
    DIVERGING   = "DIVERGING"   # subsystem drifting from integration target
    STALLED     = "STALLED"     # integration progress has stopped
    CONVERGING  = "CONVERGING"  # on track
    INTEGRATED  = "INTEGRATED"  # fully wired and observable


class SystemGovernanceSeverity(StrEnum):
    INFO     = "INFO"
    WARNING  = "WARNING"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True, slots=True)
class ContractViolation:
    """A runtime inter-subsystem contract violation."""
    ts_ns: int
    source: str                     # subsystem that produced the violation
    target: str                     # subsystem that expected the contract
    kind: ContractViolationKind
    severity: SystemGovernanceSeverity
    detail: str = ""


@dataclass(frozen=True, slots=True)
class TopologyViolation:
    """An illegal module topology event."""
    ts_ns: int
    importer: str                   # module doing the importing
    importee: str                   # module being illegally imported
    kind: TopologyViolationKind
    severity: SystemGovernanceSeverity
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ReplayIntegrityResult:
    """Result of a deterministic replay validation."""
    ts_ns: int
    event_id: str
    deterministic: bool
    non_deterministic_elements: tuple[str, ...] = ()  # e.g. "wall_ns", "random.Random"
    replay_hash: str = ""
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ConvergenceRecord:
    """Convergence status of a single subsystem."""
    ts_ns: int
    subsystem: str
    state: ConvergenceState
    has_contracts: bool             # exposes typed inter-subsystem contracts
    emits_audit_events: bool        # writes governance events to ledger
    observable: bool                # has observability endpoint / snapshot()
    supports_replay: bool           # deterministic event source
    operator_visible: bool          # operator can see its state
    integration_score: float        # 0.0 = isolated … 1.0 = fully integrated
    detail: str = ""


@dataclass(frozen=True, slots=True)
class DependencyValidationResult:
    """Result of a dependency contract check for a module."""
    ts_ns: int
    module: str
    declared_deps: tuple[str, ...]
    runtime_deps: tuple[str, ...]
    undeclared: tuple[str, ...]     # in runtime but not declared
    missing: tuple[str, ...]        # declared but not importable
    passed: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class RuntimeConsistencyReport:
    """Cross-subsystem state consistency check result."""
    ts_ns: int
    check_name: str
    consistent: bool
    divergent_subsystems: tuple[str, ...] = ()
    severity: SystemGovernanceSeverity = SystemGovernanceSeverity.INFO
    detail: str = ""


@dataclass(frozen=True, slots=True)
class SystemGovernanceStatus:
    """Aggregate snapshot of all system governance guards."""
    ts_ns: int
    overall_healthy: bool
    contracts_healthy: bool
    topology_clean: bool
    replay_deterministic: bool
    convergence_score: float        # 0.0 = fragmented … 1.0 = fully integrated
    consistency_ok: bool
    dependencies_valid: bool
    active_violations: int
    detail: str = ""


__all__ = [
    "ContractViolationKind",
    "TopologyViolationKind",
    "ConvergenceState",
    "SystemGovernanceSeverity",
    "ContractViolation",
    "TopologyViolation",
    "ReplayIntegrityResult",
    "ConvergenceRecord",
    "DependencyValidationResult",
    "RuntimeConsistencyReport",
    "SystemGovernanceStatus",
]

"""evolution_engine.lifecycle — Closed-loop evolution lifecycle package.

Stage 7 of the DIX VISION v42.2 build: enforces "No direct uncontrolled mutation."

All mutations MUST enter via:
    get_evolution_lifecycle_coordinator().submit_proposal(...)

Stage sequence:
    PROPOSED → SANDBOX → SIMULATION → BENCHMARK → GOV_REVIEW
    → PROMOTED → REPLAY_AUDIT → DEPLOYED   (happy path)
    → ROLLED_BACK → REPLAY_AUDIT           (rollback path)
    → REJECTED                              (any gate failure)
"""

from evolution_engine.lifecycle.contracts import (
    AuditEntry,
    BenchmarkResult,
    DeploymentRecord,
    GovernanceDecision,
    LifecycleStage,
    ProposalRecord,
    RollbackRecord,
    STAGE_ORDER,
    TERMINAL_STAGES,
    SandboxResult,
    SimulationResult,
)
from evolution_engine.lifecycle.coordinator import (
    EvolutionLifecycleCoordinator,
    get_evolution_lifecycle_coordinator,
)
from evolution_engine.lifecycle.audit import ReplayAuditTrail, get_replay_audit_trail
from evolution_engine.lifecycle.benchmark import BenchmarkEngine, get_benchmark_engine
from evolution_engine.lifecycle.deployment import DeploymentGate, get_deployment_gate
from evolution_engine.lifecycle.rollback import RollbackEngine, get_rollback_engine
from evolution_engine.lifecycle.sandbox import SandboxRunner, get_sandbox_runner
from evolution_engine.lifecycle.simulation import SimulationEvaluator, get_simulation_evaluator

__all__ = [
    # Contracts
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
    # Stage executors
    "BenchmarkEngine",
    "DeploymentGate",
    "ReplayAuditTrail",
    "RollbackEngine",
    "SandboxRunner",
    "SimulationEvaluator",
    # Singletons
    "EvolutionLifecycleCoordinator",
    "get_benchmark_engine",
    "get_deployment_gate",
    "get_evolution_lifecycle_coordinator",
    "get_replay_audit_trail",
    "get_rollback_engine",
    "get_sandbox_runner",
    "get_simulation_evaluator",
]

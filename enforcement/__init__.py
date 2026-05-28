"""enforcement — Non-bypassable domain boundary guards (P0-1c façade).

Re-exports canonical enforcement primitives so callers import from a
single surface without coupling to internal module paths.
"""

from .decorators import enforce_full, enforce_governance, record_attribution
from .kill_switch import arm, disarm, is_armed, trigger
from .policy_enforcer import PolicyEnforcer, get_policy_enforcer
from .runtime_guardian import get_runtime_guardian, start_runtime_guardian

# Canonical re-exports (P0-1c): thin aliases — no new state introduced.
from core.constraint_engine import (
    CompiledRule,
    RuleAction,
    RuleGraph,
    RuleKind,
    RuleSeverity,
    compile_rules,
)
from core.contracts.learning_evolution_freeze import (
    LearningEvolutionFreezePolicy,
    LearningEvolutionFrozenError,
    assert_unfrozen,
    is_unfrozen,
)
from execution_engine.execution_gate import (
    AuthorityGuard,
    AuthorityViolation,
    UnauthorizedActorError,
)
from governance_engine.control_plane.policy_engine import (
    PolicyEngine,
    install_policy_table,
    verify_policy_table_hash,
)
from system.kill_switch import KillReason, KillRequest, KillSwitch
from system_engine.authority import (
    AuthorityActor,
    AuthorityMatrix,
    AuthorityOverride,
    ConflictRow,
    load_authority_matrix,
)

__all__ = [
    # decorators
    "enforce_governance",
    "enforce_full",
    "record_attribution",
    # runtime guardian
    "get_runtime_guardian",
    "start_runtime_guardian",
    # policy enforcer
    "get_policy_enforcer",
    "PolicyEnforcer",
    # kill switch (internal)
    "trigger",
    "is_armed",
    "arm",
    "disarm",
    # authority matrix
    "AuthorityMatrix",
    "load_authority_matrix",
    "AuthorityActor",
    "AuthorityOverride",
    "ConflictRow",
    # authority guard
    "AuthorityGuard",
    "AuthorityViolation",
    "UnauthorizedActorError",
    # policy engine
    "PolicyEngine",
    "install_policy_table",
    "verify_policy_table_hash",
    # constraint engine
    "RuleGraph",
    "compile_rules",
    "RuleKind",
    "RuleSeverity",
    "RuleAction",
    "CompiledRule",
    # learning/evolution freeze
    "LearningEvolutionFreezePolicy",
    "LearningEvolutionFrozenError",
    "assert_unfrozen",
    "is_unfrozen",
    # kill switch (canonical)
    "KillSwitch",
    "KillReason",
    "KillRequest",
]

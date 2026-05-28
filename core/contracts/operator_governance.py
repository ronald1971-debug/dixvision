"""
core/contracts/operator_governance.py
DIX VISION v42.2 — Operator Governance contract types.

The operator is the constitutional authority layer of DIX VISION. No
autonomous subsystem may supersede operator sovereignty. These contracts
define the data objects that cross the boundary between the operator
governance layer and all other subsystems.

Protections formalised here:
  1. Constitutional Authority   — operator retains supreme authority at all times
  2. Override Priority          — higher-priority overrides always supersede lower
  3. Escalation Gating          — autonomy escalation requires explicit consent
  4. Manual Lockout             — operator can halt any subsystem at any time
  5. Consent Routing            — no autonomous action without consent record
  6. Governance Visibility      — all governance actions remain visible to operator
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class AuthorityLevel(StrEnum):
    CONSTITUTIONAL  = "CONSTITUTIONAL"  # full operator, no system can override
    ADMINISTRATIVE  = "ADMINISTRATIVE"  # delegated authority, system-bounded
    OBSERVER        = "OBSERVER"        # read-only, no mutation rights


class OverridePriority(StrEnum):
    """Operator override priority tiers — higher ordinal wins."""
    KILL_SWITCH         = "KILL_SWITCH"         # 5 — absolute, always wins
    MODE_LOCK           = "MODE_LOCK"           # 4 — freeze mode FSM
    EXECUTION_HALT      = "EXECUTION_HALT"      # 3 — halt execution path
    PARAMETER_OVERRIDE  = "PARAMETER_OVERRIDE"  # 2 — parameter bound override
    SUGGESTION          = "SUGGESTION"          # 1 — advisory, may be ignored

    def ordinal(self) -> int:
        _ORDER = {
            "KILL_SWITCH": 5,
            "MODE_LOCK": 4,
            "EXECUTION_HALT": 3,
            "PARAMETER_OVERRIDE": 2,
            "SUGGESTION": 1,
        }
        return _ORDER[self.value]


class LockoutScope(StrEnum):
    ALL             = "ALL"             # halt everything
    EXECUTION       = "EXECUTION"       # halt execution path only
    LEARNING        = "LEARNING"        # halt learning/evolution only
    AUTONOMOUS_OPS  = "AUTONOMOUS_OPS"  # halt autonomous ops only


class ConsentOutcome(StrEnum):
    APPROVED = "APPROVED"
    DENIED   = "DENIED"
    TIMEOUT  = "TIMEOUT"
    PENDING  = "PENDING"


@dataclass(frozen=True, slots=True)
class AuthorityAssertion:
    """Record of an operator authority assertion or validation."""
    ts_ns: int
    authority_level: AuthorityLevel
    principal: str              # who is asserting (e.g. "operator", "system_x")
    action: str                 # what action is being authorised
    granted: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class OverrideRecord:
    """A currently-active operator override."""
    override_id: str
    ts_ns: int
    priority: OverridePriority
    issuer: str                 # "operator" or delegated subsystem id
    target: str                 # which subsystem is overridden
    payload: str                # JSON-encoded or descriptive payload
    expires_ns: int = 0         # 0 = permanent until explicitly removed


@dataclass(frozen=True, slots=True)
class EscalationRequest:
    """A subsystem's request to escalate its autonomy level."""
    request_id: str
    ts_ns: int
    requester: str              # which subsystem is requesting escalation
    from_level: str             # current autonomy level
    to_level: str               # requested autonomy level
    rationale: str
    approved: bool = False
    operator_id: str = ""       # operator who approved/denied


@dataclass(frozen=True, slots=True)
class LockoutRecord:
    """State of a manual lockout."""
    lockout_id: str
    ts_ns: int
    scope: LockoutScope
    reason: str
    active: bool
    issued_by: str              # "operator" or authority level
    lifted_ts_ns: int = 0       # 0 = still active


@dataclass(frozen=True, slots=True)
class ConsentRequest:
    """Pending consent request awaiting operator decision."""
    request_id: str
    ts_ns: int
    action_kind: str            # e.g. "MODE_TRANSITION", "LEARNING_UPDATE"
    requester: str
    description: str
    timeout_ns: int             # absolute timestamp when request expires
    outcome: ConsentOutcome = ConsentOutcome.PENDING


@dataclass(frozen=True, slots=True)
class ConsentDecision:
    """Resolved consent decision."""
    request_id: str
    ts_ns: int
    outcome: ConsentOutcome
    decided_by: str             # "operator" or "timeout"
    note: str = ""


@dataclass(frozen=True, slots=True)
class VisibilityRecord:
    """Visibility score for a subsystem's governance actions."""
    subsystem: str
    ts_ns: int
    events_expected: int
    events_visible: int
    visibility_score: float     # 0.0 = blind, 1.0 = fully visible
    suppressed_count: int = 0
    healthy: bool = True


@dataclass(frozen=True, slots=True)
class OperatorGovernanceStatus:
    """Aggregate snapshot of all operator governance guards."""
    ts_ns: int
    overall_healthy: bool
    authority_intact: bool
    no_unauthorized_escalation: bool
    no_active_lockout_breach: bool
    consent_backlog: int        # number of pending consent requests
    visibility_healthy: bool
    active_overrides: int
    detail: str = ""


__all__ = [
    "AuthorityLevel",
    "OverridePriority",
    "LockoutScope",
    "ConsentOutcome",
    "AuthorityAssertion",
    "OverrideRecord",
    "EscalationRequest",
    "LockoutRecord",
    "ConsentRequest",
    "ConsentDecision",
    "VisibilityRecord",
    "OperatorGovernanceStatus",
]

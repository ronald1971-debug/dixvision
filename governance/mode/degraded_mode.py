"""governance.mode.degraded_mode — DEGRADED Mode Handler.

DEGRADED mode activates when system health drops below safe thresholds
but hasn't reached emergency halt conditions. In this mode:
- Execution is reduced (only exits + risk-reduction allowed)
- Learning continues but at reduced rate
- All new entries blocked
- Kill switch auto-arms
- Governance checks escalate to L3 for all operations

Triggers:
- Engine health < 50% for any critical engine
- Drift oracle score > 0.7
- 3+ consecutive losses
- API/connectivity degradation

Transitions:
- → SAFE_MODE: if health recovers above threshold
- → EMERGENCY_HALT: if conditions worsen
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DegradedModePolicy:
    """Policy constraints during DEGRADED mode."""

    new_entries_allowed: bool = False
    exits_allowed: bool = True
    risk_reduction_allowed: bool = True
    learning_rate_multiplier: float = 0.3
    governance_min_tier: str = "L3"
    kill_switch_armed: bool = True
    health_recovery_threshold: float = 0.7
    halt_degradation_threshold: float = 0.2
    allowed_transitions: tuple[str, ...] = ("SAFE_MODE", "EMERGENCY_HALT")


DEGRADED_MODE_POLICY = DegradedModePolicy()


def enter_degraded_mode(current_state: dict[str, Any]) -> dict[str, Any]:
    """Apply DEGRADED mode constraints to runtime state.

    Called by StateTransitionManager on health degradation.
    """
    return {
        **current_state,
        "mode": "DEGRADED",
        "execution_live": False,
        "execution_paper": True,
        "new_entries_blocked": True,
        "exits_allowed": True,
        "learning_rate_multiplier": DEGRADED_MODE_POLICY.learning_rate_multiplier,
        "governance_min_tier": "L3",
        "kill_switch_armed": True,
    }


def validate_degraded_mode(state: dict[str, Any]) -> tuple[bool, str]:
    """Validate state consistency with DEGRADED mode constraints."""
    if state.get("new_entries_blocked") is False:
        return False, "DEGRADED violation: new entries must be blocked"
    if not state.get("kill_switch_armed", True):
        return False, "DEGRADED violation: kill switch must be armed"
    return True, "DEGRADED:valid"


def should_recover(health_score: float) -> bool:
    """Check if health has recovered enough to transition back to SAFE_MODE."""
    return health_score >= DEGRADED_MODE_POLICY.health_recovery_threshold


def should_halt(health_score: float) -> bool:
    """Check if conditions have worsened enough for EMERGENCY_HALT."""
    return health_score <= DEGRADED_MODE_POLICY.halt_degradation_threshold


def exit_degraded_mode(current_state: dict[str, Any]) -> dict[str, Any]:
    """Remove DEGRADED mode constraints when health recovers.

    Called by StateTransitionManager on recovery.
    """
    return {
        **current_state,
        "mode": current_state.get("target_mode", "SAFE_MODE"),
        "new_entries_blocked": False,
        "exits_allowed": True,
        "learning_rate_multiplier": 1.0,
        "governance_min_tier": "L2",
        "kill_switch_armed": False,
    }


def can_transition_to(target_mode: str) -> tuple[bool, str]:
    """Check if transition from DEGRADED to target is allowed."""
    if target_mode in DEGRADED_MODE_POLICY.allowed_transitions:
        return True, f"DEGRADED→{target_mode}:allowed"
    return False, f"DEGRADED→{target_mode}:denied"


__all__ = [
    "DEGRADED_MODE_POLICY",
    "DegradedModePolicy",
    "can_transition_to",
    "enter_degraded_mode",
    "exit_degraded_mode",
    "should_halt",
    "should_recover",
    "validate_degraded_mode",
]

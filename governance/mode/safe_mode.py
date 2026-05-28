"""governance.mode.safe_mode — SAFE_MODE Handler.

SAFE_MODE is the initial boot state and the default recovery target.
In this mode:
- All execution is PAPER only (no live orders)
- Learning is FULL (system can learn freely)
- All governance checks at L2 minimum
- No position size limits relaxed
- Kill switch sensitivity at maximum

Transitions:
- → PAPER: via StateTransitionManager after operator authority check
- → DEGRADED: auto-transition if health drops below threshold
- → EMERGENCY_HALT: if kill switch triggered
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SafeModePolicy:
    """Policy constraints enforced during SAFE_MODE."""

    execution_allowed: bool = False
    paper_execution_allowed: bool = True
    learning_allowed: bool = True
    max_governance_tier: str = "L2"
    kill_switch_sensitivity: float = 1.0
    auto_degrade_health_threshold: float = 0.5
    allowed_transitions: tuple[str, ...] = ("PAPER", "DEGRADED", "EMERGENCY_HALT")


SAFE_MODE_POLICY = SafeModePolicy()


def enter_safe_mode(current_state: dict[str, Any]) -> dict[str, Any]:
    """Apply SAFE_MODE constraints to runtime state.

    Called by StateTransitionManager when transitioning TO safe mode.
    """
    return {
        **current_state,
        "mode": "SAFE_MODE",
        "execution_live": False,
        "execution_paper": True,
        "learning_enabled": True,
        "governance_min_tier": "L2",
        "kill_switch_sensitivity": SAFE_MODE_POLICY.kill_switch_sensitivity,
    }


def validate_safe_mode(state: dict[str, Any]) -> tuple[bool, str]:
    """Validate that state is consistent with SAFE_MODE constraints."""
    if state.get("execution_live"):
        return False, "SAFE_MODE violation: live execution must be disabled"
    if state.get("mode") != "SAFE_MODE":
        return False, f"Mode mismatch: expected SAFE_MODE, got {state.get('mode')}"
    return True, "SAFE_MODE:valid"


def exit_safe_mode(current_state: dict[str, Any]) -> dict[str, Any]:
    """Remove SAFE_MODE constraints, returning to a neutral state.

    Called by StateTransitionManager when transitioning OUT of safe mode.
    """
    return {
        **current_state,
        "mode": current_state.get("target_mode", "NORMAL"),
        "execution_live": False,
        "execution_paper": True,
        "learning_enabled": True,
    }


def can_transition_to(target_mode: str) -> tuple[bool, str]:
    """Check if transition from SAFE_MODE to target is allowed."""
    if target_mode in SAFE_MODE_POLICY.allowed_transitions:
        return True, f"SAFE_MODE→{target_mode}:allowed"
    return False, f"SAFE_MODE→{target_mode}:denied"


__all__ = [
    "SAFE_MODE_POLICY",
    "SafeModePolicy",
    "can_transition_to",
    "enter_safe_mode",
    "exit_safe_mode",
    "validate_safe_mode",
]

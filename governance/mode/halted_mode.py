"""governance.mode.halted_mode — EMERGENCY_HALT Mode Handler.

EMERGENCY_HALT is the maximum protection state. Triggered by:
- Kill switch activation
- Safety axiom breach (drawdown > MAX_DRAWDOWN_FLOOR_PCT)
- Integrity failure (ledger corruption, hash mismatch)
- Operator manual emergency stop

In this mode:
- ALL execution halted (paper + live)
- ALL learning halted
- ALL new intents rejected
- Only operator can resume (via explicit authority grant)
- System writes halt reason + timestamp to ledger
- Cooldown enforced (KILL_SWITCH_COOLDOWN_MS)

Recovery:
- ONLY via operator explicit resume through OperatorInterfaceBridge
- Requires full health check pass before transition
- Transition target: SAFE_MODE only (never directly to PAPER/LIVE)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from system import time_source


@dataclass(frozen=True, slots=True)
class HaltedModePolicy:
    """Policy constraints during EMERGENCY_HALT."""

    all_execution_halted: bool = True
    all_learning_halted: bool = True
    all_intents_rejected: bool = True
    operator_resume_required: bool = True
    cooldown_ms: float = 60_000.0
    recovery_target: str = "SAFE_MODE"
    health_check_required: bool = True
    allowed_transitions: tuple[str, ...] = ("SAFE_MODE",)


HALTED_MODE_POLICY = HaltedModePolicy()


@dataclass(frozen=True, slots=True)
class HaltEvent:
    """Record of why the system halted."""

    reason: str
    trigger_source: str
    ts_ns: int = field(default_factory=time_source.wall_ns)
    operator_id: str = ""
    severity: str = "CRITICAL"


_halt_history: list[HaltEvent] = []
_last_halt_ns: int = 0


def enter_halted_mode(
    current_state: dict[str, Any], *, reason: str = "unknown", trigger: str = "system"
) -> dict[str, Any]:
    """Apply EMERGENCY_HALT constraints to runtime state.

    Called by StateTransitionManager on kill switch or axiom breach.
    Records the halt event for forensic analysis.
    """
    global _last_halt_ns
    _last_halt_ns = time_source.wall_ns()

    event = HaltEvent(
        reason=reason,
        trigger_source=trigger,
        ts_ns=_last_halt_ns,
    )
    _halt_history.append(event)

    return {
        **current_state,
        "mode": "EMERGENCY_HALT",
        "execution_live": False,
        "execution_paper": False,
        "learning_enabled": False,
        "new_entries_blocked": True,
        "exits_allowed": False,
        "kill_switch_active": True,
        "halt_reason": reason,
        "halt_trigger": trigger,
        "halt_ts_ns": _last_halt_ns,
    }


def validate_halted_mode(state: dict[str, Any]) -> tuple[bool, str]:
    """Validate state is consistent with EMERGENCY_HALT constraints."""
    if state.get("execution_live") or state.get("execution_paper"):
        return False, "HALT violation: all execution must be disabled"
    if state.get("learning_enabled"):
        return False, "HALT violation: learning must be disabled"
    if not state.get("kill_switch_active", True):
        return False, "HALT violation: kill switch must remain active"
    return True, "EMERGENCY_HALT:valid"


def can_resume(*, operator_authorized: bool = False, health_score: float = 0.0) -> tuple[bool, str]:
    """Check if the system can resume from EMERGENCY_HALT.

    Requires:
    1. Operator explicit authorization
    2. Health check pass (score > 0.8)
    3. Cooldown period elapsed
    """
    if not operator_authorized:
        return False, "HALT:resume_denied:operator_auth_required"

    if health_score < 0.8:
        return False, f"HALT:resume_denied:health_{health_score:.2f}<0.8"

    elapsed_ms = (time_source.wall_ns() - _last_halt_ns) / 1_000_000
    if elapsed_ms < HALTED_MODE_POLICY.cooldown_ms:
        remaining = HALTED_MODE_POLICY.cooldown_ms - elapsed_ms
        return False, f"HALT:resume_denied:cooldown_{remaining:.0f}ms_remaining"

    return True, "HALT:resume_allowed→SAFE_MODE"


def can_transition_to(target_mode: str) -> tuple[bool, str]:
    """Check if transition from EMERGENCY_HALT to target is allowed."""
    if target_mode in HALTED_MODE_POLICY.allowed_transitions:
        return True, f"EMERGENCY_HALT→{target_mode}:allowed"
    return False, f"EMERGENCY_HALT→{target_mode}:denied"


def get_halt_history() -> list[HaltEvent]:
    """Retrieve all halt events for forensic analysis."""
    return list(_halt_history)


__all__ = [
    "HALTED_MODE_POLICY",
    "HaltEvent",
    "HaltedModePolicy",
    "can_resume",
    "can_transition_to",
    "enter_halted_mode",
    "get_halt_history",
    "validate_halted_mode",
]

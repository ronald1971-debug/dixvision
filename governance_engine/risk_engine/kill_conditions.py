"""Kill switch condition evaluator — pure function, no I/O."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class KillCondition(StrEnum):
    DRAWDOWN_BREACH = "DRAWDOWN_BREACH"
    EXPOSURE_BREACH = "EXPOSURE_BREACH"
    POSITION_BREACH = "POSITION_BREACH"
    MANUAL_HALT = "MANUAL_HALT"
    HAZARD_CRITICAL = "HAZARD_CRITICAL"


@dataclass(frozen=True, slots=True)
class KillEvaluation:
    """Result of evaluating all kill-switch conditions."""

    triggered: bool
    condition: KillCondition | None
    reason: str


def evaluate_kill_conditions(
    *,
    drawdown_ok: bool,
    exposure_ok: bool,
    position_ok: bool,
    manual_halt: bool,
    hazard_critical: bool,
) -> KillEvaluation:
    """Pure function — returns the first triggered kill condition, if any.

    Priority order: MANUAL_HALT > HAZARD_CRITICAL > DRAWDOWN_BREACH >
    EXPOSURE_BREACH > POSITION_BREACH.
    """
    if manual_halt:
        return KillEvaluation(
            triggered=True,
            condition=KillCondition.MANUAL_HALT,
            reason="manual halt requested",
        )
    if hazard_critical:
        return KillEvaluation(
            triggered=True,
            condition=KillCondition.HAZARD_CRITICAL,
            reason="critical hazard detected",
        )
    if not drawdown_ok:
        return KillEvaluation(
            triggered=True,
            condition=KillCondition.DRAWDOWN_BREACH,
            reason="drawdown threshold breached",
        )
    if not exposure_ok:
        return KillEvaluation(
            triggered=True,
            condition=KillCondition.EXPOSURE_BREACH,
            reason="exposure limit breached",
        )
    if not position_ok:
        return KillEvaluation(
            triggered=True,
            condition=KillCondition.POSITION_BREACH,
            reason="position limit breached",
        )
    return KillEvaluation(triggered=False, condition=None, reason="")


__all__ = ["KillCondition", "KillEvaluation", "evaluate_kill_conditions"]

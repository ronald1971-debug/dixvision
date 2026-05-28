"""Real-time risk engine — thin coordinator over position/drawdown/exposure/kill.

Pure function of inputs — no I/O, no wall-clock reads (INV-15).
"""

from __future__ import annotations

from dataclasses import dataclass

from governance_engine.risk_engine.drawdown_guard import DrawdownGuard
from governance_engine.risk_engine.exposure_limits import ExposureLimits
from governance_engine.risk_engine.kill_conditions import evaluate_kill_conditions
from governance_engine.risk_engine.position_limits import PositionLimits


@dataclass(frozen=True, slots=True)
class RiskState:
    """Immutable snapshot of the real-time risk evaluation."""

    halted: bool
    breach_reason: str
    position_ok: bool
    drawdown_ok: bool
    exposure_ok: bool


class RealTimeRiskEngine:
    """Coordinates position, drawdown, and exposure checks into one RiskState.

    ``evaluate`` is a pure function of its inputs — all thresholds are
    set at construction time.
    """

    __slots__ = ("_position_limits", "_drawdown_guard", "_exposure_limits")

    def __init__(
        self,
        max_drawdown_pct: float = 0.05,
        max_exposure_notional: float = 1_000_000.0,
        max_position_qty: float = 100.0,
    ) -> None:
        self._position_limits = PositionLimits(max_qty=max_position_qty)
        self._drawdown_guard = DrawdownGuard(threshold_pct=max_drawdown_pct)
        self._exposure_limits = ExposureLimits(max_notional=max_exposure_notional)

    def evaluate(
        self,
        position_qty: float,
        notional: float,
        drawdown_pct: float,
    ) -> RiskState:
        """Return a :class:`RiskState` for the given market snapshot."""
        pos_result = self._position_limits.check(position_qty)
        dd_result = self._drawdown_guard.check(drawdown_pct)
        exp_result = self._exposure_limits.check(notional)

        kill = evaluate_kill_conditions(
            drawdown_ok=dd_result.passed,
            exposure_ok=exp_result.passed,
            position_ok=pos_result.passed,
            manual_halt=False,
            hazard_critical=False,
        )

        return RiskState(
            halted=kill.triggered,
            breach_reason=kill.reason,
            position_ok=pos_result.passed,
            drawdown_ok=dd_result.passed,
            exposure_ok=exp_result.passed,
        )


__all__ = ["RiskState", "RealTimeRiskEngine"]

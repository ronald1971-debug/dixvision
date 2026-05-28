"""Cockpit API — /risk endpoint.

Returns current risk metrics: position limits, drawdown, exposure,
kill conditions. Read-only. B1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["RiskSnapshot", "RiskProvider"]


@dataclass(frozen=True, slots=True)
class PositionRisk:
    symbol: str
    current_qty: float
    limit_qty: float
    utilisation_pct: float


@dataclass(frozen=True, slots=True)
class RiskSnapshot:
    ts_ns: int
    total_exposure_usd: float
    max_exposure_usd: float
    exposure_utilisation_pct: float
    current_drawdown_pct: float
    drawdown_limit_pct: float
    positions: tuple[PositionRisk, ...]
    kill_condition_triggered: bool
    kill_condition_reason: str


class RiskProvider:
    """Assembles RiskSnapshot from injected risk-engine state."""

    def __init__(self, risk_engine: Any) -> None:
        self._risk = risk_engine

    def get_snapshot(self, ts_ns: int) -> RiskSnapshot:
        state = self._risk.current_state()
        positions = tuple(
            PositionRisk(
                symbol=p.symbol,
                current_qty=p.qty,
                limit_qty=p.limit,
                utilisation_pct=abs(p.qty) / p.limit * 100 if p.limit > 0 else 0.0,
            )
            for p in state.positions
        )
        exp_pct = (state.total_exposure / state.max_exposure * 100
                   if state.max_exposure > 0 else 0.0)
        return RiskSnapshot(
            ts_ns=ts_ns,
            total_exposure_usd=state.total_exposure,
            max_exposure_usd=state.max_exposure,
            exposure_utilisation_pct=exp_pct,
            current_drawdown_pct=state.current_drawdown_pct,
            drawdown_limit_pct=state.drawdown_limit_pct,
            positions=positions,
            kill_condition_triggered=state.kill_triggered,
            kill_condition_reason=state.kill_reason,
        )

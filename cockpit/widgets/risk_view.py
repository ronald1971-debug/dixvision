"""Cockpit widget — risk dashboard view.

Aggregates and formats risk data for the operator dashboard.
Read-only. B1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["RiskViewWidget", "RiskViewState"]


@dataclass(frozen=True, slots=True)
class RiskBar:
    label: str
    current: float
    limit: float
    pct_used: float
    status: str    # "OK" | "WARNING" | "CRITICAL"


@dataclass(frozen=True, slots=True)
class RiskViewState:
    ts_ns: int
    bars: tuple[RiskBar, ...]
    alert_count: int
    kill_switch_armed: bool


def _bar_status(pct: float) -> str:
    if pct >= 90:
        return "CRITICAL"
    if pct >= 70:
        return "WARNING"
    return "OK"


class RiskViewWidget:
    """Read interface for risk dashboard rendering."""

    def __init__(self, risk_provider: Any) -> None:
        self._risk = risk_provider

    def get_state(self, ts_ns: int) -> RiskViewState:
        snap = self._risk.get_snapshot(ts_ns)
        bars: list[RiskBar] = [
            RiskBar(
                label="Exposure",
                current=snap.total_exposure_usd,
                limit=snap.max_exposure_usd,
                pct_used=snap.exposure_utilisation_pct,
                status=_bar_status(snap.exposure_utilisation_pct),
            ),
            RiskBar(
                label="Drawdown",
                current=snap.current_drawdown_pct,
                limit=snap.drawdown_limit_pct,
                pct_used=(snap.current_drawdown_pct / snap.drawdown_limit_pct * 100
                           if snap.drawdown_limit_pct > 0 else 0.0),
                status=_bar_status(snap.current_drawdown_pct / snap.drawdown_limit_pct * 100
                                    if snap.drawdown_limit_pct > 0 else 0.0),
            ),
        ]
        for pos in snap.positions:
            bars.append(RiskBar(
                label=pos.symbol,
                current=abs(pos.current_qty),
                limit=pos.limit_qty,
                pct_used=pos.utilisation_pct,
                status=_bar_status(pos.utilisation_pct),
            ))
        alerts = sum(1 for b in bars if b.status != "OK")
        return RiskViewState(
            ts_ns=ts_ns, bars=tuple(bars),
            alert_count=alerts,
            kill_switch_armed=snap.kill_condition_triggered,
        )

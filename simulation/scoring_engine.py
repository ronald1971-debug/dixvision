"""simulation/scoring_engine.py
DIX VISION v42.2 — Simulation Scoring Engine

Scores simulation runs against multiple performance metrics and
produces a composite SimulationScore. Used by the strategy arena
and genetic evolution engine to rank candidate strategies.

composite_score = 0.35*sharpe + 0.25*calmar + 0.2*win_rate
               + 0.1*profit_factor + 0.1*recovery_factor

Pure functions + frozen dataclasses (INV-15). No IO.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TradeResult:
    """One closed trade result from a simulation run."""
    strategy_id: str
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    qty: float
    pnl: float
    entry_ts_ns: int
    exit_ts_ns: int
    regime: str


@dataclass(frozen=True, slots=True)
class SimulationScore:
    """Composite performance score for a simulation run."""
    strategy_id: str
    scenario_id: str
    num_trades: int
    total_pnl: float
    win_rate: float
    sharpe: float
    calmar: float
    profit_factor: float
    max_drawdown: float
    max_drawdown_duration_bars: int
    recovery_factor: float
    composite_score: float
    ts_ns: int


def _sharpe(returns: list[float]) -> float:
    n = len(returns)
    if n < 2:
        return 0.0
    mean = sum(returns) / n
    var = sum((r - mean) ** 2 for r in returns) / n
    std = math.sqrt(var) if var > 1e-12 else 1.0
    return mean / std * math.sqrt(252)  # annualised (daily returns assumed)


def _max_drawdown(equity_curve: list[float]) -> tuple[float, int]:
    """Returns (max_dd_fraction, max_dd_duration_bars)."""
    if len(equity_curve) < 2:
        return 0.0, 0
    peak = equity_curve[0]
    max_dd = 0.0
    dd_start = 0
    max_duration = 0
    current_start = 0
    for i, val in enumerate(equity_curve):
        if val > peak:
            peak = val
            current_start = i
        dd = (peak - val) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
            max_duration = i - current_start
    return max_dd, max_duration


def _calmar(total_return: float, max_dd: float, num_years: float = 1.0) -> float:
    if max_dd < 1e-8:
        return 0.0
    annual_return = total_return / num_years
    return annual_return / max_dd


def score_simulation(
    strategy_id: str,
    scenario_id: str,
    trades: list[TradeResult],
    initial_capital: float = 100_000.0,
    ts_ns: int = 0,
) -> SimulationScore:
    """Score a list of closed trades from a simulation run."""
    if not trades:
        return SimulationScore(
            strategy_id=strategy_id,
            scenario_id=scenario_id,
            num_trades=0,
            total_pnl=0.0,
            win_rate=0.0,
            sharpe=0.0,
            calmar=0.0,
            profit_factor=0.0,
            max_drawdown=0.0,
            max_drawdown_duration_bars=0,
            recovery_factor=0.0,
            composite_score=0.0,
            ts_ns=ts_ns,
        )

    pnls = [t.pnl for t in trades]
    total_pnl = sum(pnls)
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p <= 0)
    win_rate = wins / len(pnls)

    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss = abs(sum(p for p in pnls if p < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 1e-8 else float("inf")
    profit_factor = min(profit_factor, 10.0)  # cap for scoring

    # Build equity curve
    equity = initial_capital
    equity_curve = [equity]
    for pnl in pnls:
        equity += pnl
        equity_curve.append(equity)

    max_dd, max_dd_dur = _max_drawdown(equity_curve)
    returns = [pnls[i] / equity_curve[i] for i in range(len(pnls))]
    sharpe = _sharpe(returns)
    total_return = total_pnl / initial_capital
    calmar = _calmar(total_return, max_dd)
    recovery = total_return / max_dd if max_dd > 1e-8 else 0.0

    # Composite score (all inputs normalised to [0,1])
    sharpe_norm = min(1.0, max(0.0, (sharpe + 3.0) / 6.0))
    calmar_norm = min(1.0, max(0.0, calmar / 5.0))
    pf_norm = min(1.0, max(0.0, (profit_factor - 1.0) / 4.0))
    rec_norm = min(1.0, max(0.0, recovery / 3.0))
    composite = (
        0.35 * sharpe_norm
        + 0.25 * calmar_norm
        + 0.20 * win_rate
        + 0.10 * pf_norm
        + 0.10 * rec_norm
    )

    return SimulationScore(
        strategy_id=strategy_id,
        scenario_id=scenario_id,
        num_trades=len(trades),
        total_pnl=total_pnl,
        win_rate=win_rate,
        sharpe=sharpe,
        calmar=calmar,
        profit_factor=profit_factor,
        max_drawdown=max_dd,
        max_drawdown_duration_bars=max_dd_dur,
        recovery_factor=recovery,
        composite_score=composite,
        ts_ns=ts_ns,
    )


__all__ = [
    "SimulationScore",
    "TradeResult",
    "score_simulation",
]

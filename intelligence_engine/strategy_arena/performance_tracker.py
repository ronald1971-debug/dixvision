"""PerformanceTracker — tracks real-time strategy performance metrics.

Computes Sharpe, drawdown, win-rate, and regime fitness for each
active strategy in the arena. Pure math, no IO (INV-15).
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PerformanceSnapshot:
    """Point-in-time performance metrics for a strategy."""

    strategy_id: str
    ts_ns: int
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    current_drawdown_pct: float
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    total_trades: int
    total_pnl: float


class StrategyPerformanceWindow:
    """Rolling window performance calculator for a single strategy."""

    def __init__(self, window_size: int = 200) -> None:
        self._returns: deque[float] = deque(maxlen=window_size)
        self._peak_equity: float = 0.0
        self._equity: float = 0.0
        self._wins: int = 0
        self._losses: int = 0
        self._total_win_pnl: float = 0.0
        self._total_loss_pnl: float = 0.0
        self._total_pnl: float = 0.0

    def record_trade(self, pnl: float) -> None:
        """Record a completed trade result."""
        self._returns.append(pnl)
        self._equity += pnl
        self._total_pnl += pnl
        self._peak_equity = max(self._peak_equity, self._equity)
        if pnl > 0:
            self._wins += 1
            self._total_win_pnl += pnl
        elif pnl < 0:
            self._losses += 1
            self._total_loss_pnl += abs(pnl)

    @property
    def sharpe_ratio(self) -> float:
        """Annualized Sharpe (assumes daily returns)."""
        if len(self._returns) < 2:
            return 0.0
        returns = list(self._returns)
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        std = math.sqrt(variance) if variance > 0 else 1e-9
        return (mean / std) * math.sqrt(252)

    @property
    def sortino_ratio(self) -> float:
        """Sortino ratio (only downside deviation)."""
        if len(self._returns) < 2:
            return 0.0
        returns = list(self._returns)
        mean = sum(returns) / len(returns)
        downside = [min(r, 0) ** 2 for r in returns]
        down_dev = math.sqrt(sum(downside) / len(downside)) if downside else 1e-9
        return (mean / down_dev) * math.sqrt(252) if down_dev > 1e-9 else 0.0

    @property
    def max_drawdown_pct(self) -> float:
        """Maximum drawdown as percentage of peak."""
        if self._peak_equity <= 0:
            return 0.0
        return (self._peak_equity - self._equity) / self._peak_equity

    @property
    def win_rate(self) -> float:
        total = self._wins + self._losses
        return self._wins / total if total > 0 else 0.0

    @property
    def profit_factor(self) -> float:
        if self._total_loss_pnl == 0:
            return float("inf") if self._total_win_pnl > 0 else 0.0
        return self._total_win_pnl / self._total_loss_pnl

    def snapshot(self, strategy_id: str, ts_ns: int) -> PerformanceSnapshot:
        total = self._wins + self._losses
        return PerformanceSnapshot(
            strategy_id=strategy_id,
            ts_ns=ts_ns,
            sharpe_ratio=self.sharpe_ratio,
            sortino_ratio=self.sortino_ratio,
            max_drawdown_pct=self.max_drawdown_pct,
            current_drawdown_pct=self.max_drawdown_pct,
            win_rate=self.win_rate,
            profit_factor=self.profit_factor,
            avg_win=self._total_win_pnl / self._wins if self._wins > 0 else 0.0,
            avg_loss=self._total_loss_pnl / self._losses if self._losses > 0 else 0.0,
            total_trades=total,
            total_pnl=self._total_pnl,
        )


class PerformanceTracker:
    """Tracks performance windows for all strategies in the arena."""

    def __init__(self, window_size: int = 200) -> None:
        self._windows: dict[str, StrategyPerformanceWindow] = {}
        self._window_size = window_size

    def register_strategy(self, strategy_id: str) -> None:
        if strategy_id not in self._windows:
            self._windows[strategy_id] = StrategyPerformanceWindow(self._window_size)

    def record_trade(self, strategy_id: str, pnl: float) -> None:
        if strategy_id not in self._windows:
            self.register_strategy(strategy_id)
        self._windows[strategy_id].record_trade(pnl)

    def snapshot(self, strategy_id: str, ts_ns: int) -> PerformanceSnapshot | None:
        window = self._windows.get(strategy_id)
        if window is None:
            return None
        return window.snapshot(strategy_id, ts_ns)

    def all_snapshots(self, ts_ns: int) -> list[PerformanceSnapshot]:
        return [w.snapshot(sid, ts_ns) for sid, w in self._windows.items()]

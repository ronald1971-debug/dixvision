"""Performance tracker (BUILD-DIRECTIVE §15 — TIS module 15).

Tracks per-trader and per-atom performance over time. Every fill
attributed to a trader-sourced atom updates the performance ledger.

Performance data feeds:
- Credibility updates (good performers gain credibility)
- Reliability scoring (tracks prediction accuracy)
- Atom fitness (which atoms work in which regimes)
- Composition weighting (better atoms get higher weight)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PerformanceRecord:
    """Single performance record for a trader or atom."""

    entity_id: str  # trader_id or atom_id
    regime: str
    pnl: float
    sharpe_contribution: float
    max_drawdown: float
    win: bool
    ts_ns: int


@dataclass(slots=True)
class PerformanceSummary:
    """Aggregate performance summary."""

    entity_id: str
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    current_drawdown: float = 0.0
    peak_pnl: float = 0.0
    sharpe: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    regime_performance: dict[str, float] = field(default_factory=dict)


class PerformanceTracker:
    """Tracks performance for traders and strategy atoms.

    Thread of attribution:
    Fill → TradeOutcome → attributed atom → performance update

    All updates are append-only (replayable).
    """

    def __init__(self) -> None:
        self._records: dict[str, list[PerformanceRecord]] = {}
        self._summaries: dict[str, PerformanceSummary] = {}

    def record(
        self,
        *,
        entity_id: str,
        regime: str,
        pnl: float,
        sharpe_contribution: float = 0.0,
        max_drawdown: float = 0.0,
        ts_ns: int = 0,
    ) -> PerformanceSummary:
        """Record a performance outcome. Returns updated summary."""
        rec = PerformanceRecord(
            entity_id=entity_id,
            regime=regime,
            pnl=pnl,
            sharpe_contribution=sharpe_contribution,
            max_drawdown=max_drawdown,
            win=pnl > 0,
            ts_ns=ts_ns,
        )
        self._records.setdefault(entity_id, []).append(rec)

        # Update summary
        summary = self._summaries.get(entity_id)
        if summary is None:
            summary = PerformanceSummary(entity_id=entity_id)
            self._summaries[entity_id] = summary

        summary.total_trades += 1
        summary.total_pnl += pnl
        if pnl > 0:
            summary.wins += 1
        else:
            summary.losses += 1

        # Track drawdown
        if summary.total_pnl > summary.peak_pnl:
            summary.peak_pnl = summary.total_pnl
            summary.current_drawdown = 0.0
        else:
            summary.current_drawdown = summary.peak_pnl - summary.total_pnl
            summary.max_drawdown = max(summary.max_drawdown, summary.current_drawdown)

        # Win rate
        summary.win_rate = summary.wins / max(summary.total_trades, 1)

        # Profit factor
        gross_profit = sum(r.pnl for r in self._records[entity_id] if r.pnl > 0)
        gross_loss = abs(sum(r.pnl for r in self._records[entity_id] if r.pnl < 0))
        summary.profit_factor = gross_profit / max(gross_loss, 1e-10)

        # Regime performance
        regime_pnl = summary.regime_performance.get(regime, 0.0)
        summary.regime_performance[regime] = regime_pnl + pnl

        # Sharpe (simplified: annualized from per-trade)
        records = self._records[entity_id]
        if len(records) >= 5:
            returns = [r.pnl for r in records[-50:]]
            mean_r = sum(returns) / len(returns)
            std_r = math.sqrt(sum((r - mean_r) ** 2 for r in returns) / len(returns))
            summary.sharpe = (mean_r / std_r * math.sqrt(252)) if std_r > 0 else 0.0

        return summary

    def get_summary(self, entity_id: str) -> PerformanceSummary | None:
        """Get performance summary for an entity."""
        return self._summaries.get(entity_id)

    def get_regime_leaders(self, regime: str, *, top_n: int = 10) -> list[str]:
        """Get top performers in a specific regime."""
        scored: list[tuple[str, float]] = []
        for eid, summary in self._summaries.items():
            regime_pnl = summary.regime_performance.get(regime, 0.0)
            if regime_pnl > 0:
                scored.append((eid, regime_pnl))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [s[0] for s in scored[:top_n]]

    def get_best_atoms(self, *, min_trades: int = 10, top_n: int = 20) -> list[str]:
        """Get best-performing atoms by Sharpe ratio."""
        candidates: list[tuple[str, float]] = []
        for eid, summary in self._summaries.items():
            if summary.total_trades >= min_trades and summary.sharpe > 0:
                candidates.append((eid, summary.sharpe))
        candidates.sort(key=lambda x: x[1], reverse=True)
        return [c[0] for c in candidates[:top_n]]

    @property
    def tracked_entities(self) -> int:
        """Number of entities being tracked."""
        return len(self._summaries)

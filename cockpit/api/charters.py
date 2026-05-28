"""Cockpit API — /charters endpoint.

Returns active strategy charters: definitions, lifecycle state,
performance metrics. Read-only. B1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["CharterSummary", "CharterProvider"]


@dataclass(frozen=True, slots=True)
class CharterSummary:
    strategy_id: str
    kind: str
    lifecycle_state: str     # "SHADOW" | "ACTIVE" | "RETIRING" | "FROZEN"
    sharpe: float
    drawdown_pct: float
    win_rate: float
    trade_count: int
    plugin_chain: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CharterListResponse:
    ts_ns: int
    charters: tuple[CharterSummary, ...]


class CharterProvider:
    """Assembles CharterListResponse from registry + performance state."""

    def __init__(self, strategy_registry: Any, performance_store: Any) -> None:
        self._registry = strategy_registry
        self._perf = performance_store

    def list_charters(self, ts_ns: int) -> CharterListResponse:
        summaries: list[CharterSummary] = []
        for strategy in self._registry.all():
            perf = self._perf.get(strategy.id)
            summaries.append(CharterSummary(
                strategy_id=strategy.id,
                kind=strategy.kind,
                lifecycle_state=strategy.lifecycle_state,
                sharpe=perf.sharpe if perf else 0.0,
                drawdown_pct=perf.drawdown_pct if perf else 0.0,
                win_rate=perf.win_rate if perf else 0.0,
                trade_count=perf.trade_count if perf else 0,
                plugin_chain=tuple(strategy.plugin_chain),
            ))
        return CharterListResponse(ts_ns=ts_ns, charters=tuple(summaries))

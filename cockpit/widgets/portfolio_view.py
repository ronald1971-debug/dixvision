"""Cockpit widget — portfolio view.

Aggregates current positions, P&L, and allocation for the operator dashboard.
Read-only. B1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["PositionRow", "PortfolioViewState", "PortfolioViewWidget"]


@dataclass(frozen=True, slots=True)
class PositionRow:
    symbol: str
    qty: float
    side: str            # "LONG" | "SHORT" | "FLAT"
    avg_entry_price: float
    current_price: float
    unrealised_pnl_usd: float
    strategy_id: str


@dataclass(frozen=True, slots=True)
class PortfolioViewState:
    ts_ns: int
    positions: tuple[PositionRow, ...]
    total_unrealised_pnl_usd: float
    total_realised_pnl_usd: float
    position_count: int


class PortfolioViewWidget:
    """Read interface for portfolio view rendering."""

    def __init__(self, position_store: Any, pnl_store: Any) -> None:
        self._positions = position_store
        self._pnl = pnl_store

    def get_state(self, ts_ns: int) -> PortfolioViewState:
        raw = self._positions.all()
        rows: list[PositionRow] = []
        for p in raw:
            side = "LONG" if p.qty > 0 else ("SHORT" if p.qty < 0 else "FLAT")
            rows.append(PositionRow(
                symbol=p.symbol,
                qty=p.qty,
                side=side,
                avg_entry_price=p.avg_entry_price,
                current_price=p.current_price,
                unrealised_pnl_usd=p.unrealised_pnl_usd,
                strategy_id=p.strategy_id,
            ))
        total_unrealised = sum(r.unrealised_pnl_usd for r in rows)
        total_realised = self._pnl.total_realised_usd()
        return PortfolioViewState(
            ts_ns=ts_ns,
            positions=tuple(rows),
            total_unrealised_pnl_usd=total_unrealised,
            total_realised_pnl_usd=total_realised,
            position_count=len(rows),
        )

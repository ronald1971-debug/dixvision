"""Cockpit widget — portfolio view.

Reads live position + P&L state from the execution engine via ui.server.STATE.
No constructor injection required.
"""

from __future__ import annotations

from typing import Any

__all__ = ["portfolio_view_payload"]


def portfolio_view_payload() -> dict[str, Any]:
    try:
        from ui.server import STATE  # noqa: PLC0415
        # ExecutionEngine exposes positions via .get_positions()
        positions_raw = STATE.execution.get_positions()
        rows = []
        total_unrealised = 0.0
        for p in positions_raw:
            side = "LONG" if p.qty > 0 else ("SHORT" if p.qty < 0 else "FLAT")
            rows.append({
                "symbol": p.symbol,
                "qty": p.qty,
                "side": side,
                "avg_entry_price": p.avg_entry_price,
                "current_price": getattr(p, "current_price", 0.0),
                "unrealised_pnl_usd": getattr(p, "unrealised_pnl_usd", 0.0),
                "strategy_id": getattr(p, "strategy_id", ""),
            })
            total_unrealised += getattr(p, "unrealised_pnl_usd", 0.0)
        return {
            "positions": rows,
            "position_count": len(rows),
            "total_unrealised_pnl_usd": total_unrealised,
        }
    except Exception as exc:  # noqa: BLE001
        return {"positions": [], "position_count": 0,
                "total_unrealised_pnl_usd": 0.0, "error": str(exc)}

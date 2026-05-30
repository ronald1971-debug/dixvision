"""ui.paper_trading_routes — REST surface for the Stage 9 paper trading ecosystem.

Routes:
  GET  /api/paper/summary               — aggregate P&L + fill stats across all 6 venues
  GET  /api/paper/portfolios            — all 6 portfolio snapshots
  GET  /api/paper/portfolio/{venue}     — single venue detail (positions, fills, P&L)
  GET  /api/paper/fills/{venue}         — recent fills for one venue (default 50)
  POST /api/paper/reset/{venue}         — reset one venue's paper portfolio
  POST /api/paper/reset                 — reset all 6 paper portfolios

All reads/writes go through get_paper_trading_hub().
No execution — this is a pure observation + control surface.

Authority: ui.* only; hub is lazy-imported per B1.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from system.time_source import utc_now

_logger = logging.getLogger(__name__)


class ResetRequest(BaseModel):
    confirm: bool = False


def build_paper_trading_router() -> APIRouter:
    router = APIRouter(prefix="/api/paper", tags=["paper_trading"])

    def _hub():
        try:
            from execution_engine.paper_trading.hub import get_paper_trading_hub
            return get_paper_trading_hub()
        except Exception as exc:
            _logger.warning("paper_trading_routes: hub unavailable: %s", exc)
            return None

    @router.get("/summary")
    def get_summary() -> dict[str, Any]:
        """Aggregate P&L and fill statistics across all 6 paper venues."""
        hub = _hub()
        if hub is None:
            return _unavailable("paper_trading_hub")
        summary = hub.pnl_summary()
        summary["ts"] = utc_now().isoformat()
        return summary

    @router.get("/portfolios")
    def get_portfolios() -> dict[str, Any]:
        """All six venue portfolios: cash, positions, realized P&L, recent fills."""
        hub = _hub()
        if hub is None:
            return _unavailable("paper_trading_hub")
        snap = hub.snapshot()
        snap["ts"] = utc_now().isoformat()
        return snap

    @router.get("/portfolio/{venue}")
    def get_portfolio(venue: str) -> dict[str, Any]:
        """Single venue portfolio detail."""
        hub = _hub()
        if hub is None:
            return _unavailable("paper_trading_hub")
        port = hub.portfolio_snapshot(venue)
        if port is None:
            raise HTTPException(
                status_code=404,
                detail=f"unknown paper venue {venue!r}. "
                       f"Valid venues: binance_paper, coinbase_paper, kraken_paper, "
                       f"alpaca_paper, oanda_paper, ibkr_paper",
            )
        port["ts"] = utc_now().isoformat()
        return port

    @router.get("/fills/{venue}")
    def get_fills(venue: str, limit: int = 50) -> dict[str, Any]:
        """Recent fills for one venue (newest-first)."""
        hub = _hub()
        if hub is None:
            return _unavailable("paper_trading_hub")
        adapter = hub.adapter(venue)
        if adapter is None:
            raise HTTPException(status_code=404, detail=f"unknown paper venue {venue!r}")
        limit = min(limit, 200)
        fills = adapter.recent_fills(limit)
        from execution_engine.paper_trading.adapter import _evt_to_dict
        return {
            "venue": venue,
            "count": len(fills),
            "fills": [_evt_to_dict(f) for f in reversed(fills)],
            "ts": utc_now().isoformat(),
        }

    @router.post("/reset/{venue}")
    def reset_venue(venue: str, body: ResetRequest) -> dict[str, Any]:
        """Reset one venue's paper portfolio to its initial state.

        Clears all positions and restores initial_cash.
        Requires body.confirm=true to prevent accidental resets.
        """
        if not body.confirm:
            raise HTTPException(
                status_code=400,
                detail="set body.confirm=true to confirm portfolio reset",
            )
        hub = _hub()
        if hub is None:
            raise HTTPException(status_code=503, detail="paper trading hub unavailable")
        ok = hub.reset_venue(venue)
        if not ok:
            raise HTTPException(status_code=404, detail=f"unknown paper venue {venue!r}")
        return {
            "venue": venue,
            "result": "reset",
            "ts": utc_now().isoformat(),
        }

    @router.post("/reset")
    def reset_all(body: ResetRequest) -> dict[str, Any]:
        """Reset all six paper portfolios to initial state.

        Requires body.confirm=true.
        """
        if not body.confirm:
            raise HTTPException(
                status_code=400,
                detail="set body.confirm=true to confirm full reset",
            )
        hub = _hub()
        if hub is None:
            raise HTTPException(status_code=503, detail="paper trading hub unavailable")
        hub.reset_all()
        return {
            "result": "all_reset",
            "venue_count": 6,
            "ts": utc_now().isoformat(),
        }

    return router


def _unavailable(subsystem: str) -> dict[str, Any]:
    return {"status": "unavailable", "subsystem": subsystem, "data": {}}

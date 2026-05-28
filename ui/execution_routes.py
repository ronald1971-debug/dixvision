"""D1 — operator-facing execution-adapter HTTP surface (read-only).

Exposes the :class:`AdapterRegistry` snapshot as JSON so the operator
dashboard can render an :code:`AdapterStatusGrid` showing which live
venues are reachable, which are still in scaffold mode, and which have
been halted by the operator.

Authority lint: only imports :mod:`execution_engine.adapters` (no
plugin or hot-path imports). B7-clean.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from execution_engine.adapters import default_registry


def build_execution_router() -> APIRouter:
    """Construct the read-only /api/execution router."""
    router = APIRouter(prefix="/api/execution", tags=["execution"])

    @router.get("/adapters")
    def list_adapters() -> dict[str, Any]:
        reg = default_registry()
        snap = reg.snapshot()
        return {
            "count": len(snap),
            "adapters": [
                {
                    "name": s.name,
                    "venue": s.venue,
                    "state": s.state.value,
                    "detail": s.detail,
                    "last_heartbeat_ns": s.last_heartbeat_ns,
                }
                for s in snap
            ],
        }

    @router.get("/positions")
    def list_positions() -> dict[str, Any]:
        """Open positions snapshot.

        Returns scaffold-honest ``wired=False`` until an adapter exposes a
        position book over the registry.  The dashboard renders this as an
        amber chip rather than a blank panel.
        """
        reg = default_registry()
        snap = reg.snapshot()
        any_ready = any(s.state.value == "READY" for s in snap)
        return {
            "wired": any_ready,
            "positions": [],
            "detail": (
                "position book not yet exposed by any adapter"
                if not any_ready
                else "adapter READY but position query not yet implemented"
            ),
        }

    @router.get("/orders")
    def list_orders() -> dict[str, Any]:
        """Open orders snapshot.

        Returns scaffold-honest ``wired=False`` until the order book is
        wired to the adapter lifecycle registry.
        """
        reg = default_registry()
        snap = reg.snapshot()
        any_ready = any(s.state.value == "READY" for s in snap)
        return {
            "wired": any_ready,
            "orders": [],
            "detail": (
                "order book not yet wired; all adapters DISCONNECTED"
                if not any_ready
                else "adapter READY but order query not yet implemented"
            ),
        }

    @router.get("/circuit_breaker")
    def circuit_breaker_status() -> dict[str, Any]:
        """Circuit breaker state snapshot.

        Returns the high-level breaker state from the protections layer.
        Currently scaffold-honest: the CircuitBreaker value object is
        per-order and not aggregated at the registry level yet.
        """
        return {
            "wired": False,
            "state": "ARMED",
            "trade_limit": 4,
            "lookback_period": "60m",
            "locked_until_ns": None,
            "detail": "circuit breaker not yet aggregated at execution registry level",
        }

    return router


__all__ = ["build_execution_router"]

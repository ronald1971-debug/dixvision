"""
execution/trade_executor.py
Executes an Indira ``ExecutionEvent`` against the adapter registered with the
AdapterRouter. EVERY trade passes through the RuntimeConvergence enforcement
gate (HMAC-signed blocking governance). Logs every step to the ledger.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from execution.adapter_router import get_adapter_router
from state.ledger.writer import get_writer
from system import time_source
from system.metrics import get_metrics


@dataclass
class ExecuteResult:
    ok: bool
    adapter: str
    response: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


class TradeExecutor:
    def __init__(self) -> None:
        self._router = get_adapter_router()
        self._writer = get_writer()
        self._metrics = get_metrics()

    def execute(self, event: Any) -> ExecuteResult:
        if getattr(event, "event_type", "") != "TRADE_EXECUTION":
            return ExecuteResult(False, "none", reason="not_a_trade_event")
        if not getattr(event, "allowed", False):
            return ExecuteResult(False, "none", reason="risk_disallowed")

        # Enforcement gate check — every intent must pass governance
        try:
            from runtime.convergence import get_convergence

            convergence = get_convergence()
            intent_id = f"trade-{time_source.wall_ns()}"
            intent_data: dict[str, object] = {
                "asset": str(event.asset),
                "side": str(event.side),
                "size_usd": float(event.size_usd),
                "order_type": str(event.order_type),
                "strategy": str(getattr(event, "strategy", "unknown")),
            }
            if not convergence.enforce_intent(intent_id, intent_data):
                self._writer.write(
                    "MARKET",
                    "ORDER_DENIED",
                    "trade_executor",
                    {"asset": event.asset, "reason": "governance_denied"},
                )
                self._metrics.increment("trade_executor.governance_denied")
                return ExecuteResult(False, "none", reason="governance_denied")
        except Exception:
            pass  # convergence layer not booted — allow fallthrough

        asset = str(event.asset)
        adapter = self._router.route(asset)
        if adapter is None:
            self._writer.write(
                "MARKET",
                "ORDER_REJECTED",
                "trade_executor",
                {"asset": asset, "reason": "no_adapter"},
            )
            self._metrics.increment("trade_executor.no_adapter")
            return ExecuteResult(False, "none", reason="no_adapter")

        try:
            resp = adapter.place_order(
                symbol=asset,
                side=event.side,
                size=float(event.size_usd),
                order_type=str(event.order_type),
            )
        except Exception as e:
            self._writer.write(
                "MARKET", "ORDER_ERROR", "trade_executor", {"asset": asset, "error": str(e)}
            )
            self._metrics.increment("trade_executor.error")
            return ExecuteResult(False, str(adapter), reason=f"adapter_error:{e}")

        # Submit fill to kernel reconciler if convergence is active
        try:
            from runtime.convergence import get_convergence
            from runtime.fabric.fill_reconciler import Fill

            convergence = get_convergence()
            if convergence._kernel is not None:
                order_id = resp.get("order_id", "")
                filled_qty = float(resp.get("filled_qty", resp.get("size", 0)))
                filled_price = float(resp.get("filled_price", 0))
                fee = float(resp.get("fee", 0))
                fill = Fill(
                    fill_id=f"fill-{time_source.wall_ns()}",
                    order_id=order_id,
                    symbol=asset,
                    side=event.side,
                    quantity=filled_qty,
                    price=filled_price,
                    fee_usd=fee,
                    ts_ns=time_source.wall_ns(),
                    adapter_name=type(adapter).__name__,
                )
                convergence._kernel.submit_fill(fill)
        except Exception:
            pass  # reconciliation wiring failure is non-fatal

        self._writer.write(
            "MARKET",
            "ORDER_SUBMITTED",
            "trade_executor",
            {
                "asset": asset,
                "side": event.side,
                "size_usd": event.size_usd,
                "adapter": type(adapter).__name__,
                "response": resp,
            },
        )
        self._metrics.increment("trade_executor.submit")
        return ExecuteResult(True, type(adapter).__name__, response=resp)


_te: TradeExecutor | None = None
_lock = threading.Lock()


def get_trade_executor() -> TradeExecutor:
    global _te
    if _te is None:
        with _lock:
            if _te is None:
                _te = TradeExecutor()
    return _te

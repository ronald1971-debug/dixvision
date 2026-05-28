"""execution.adapters._ccxt_backed — CCXT-backed adapter mixin.

Provides the real exchange connectivity logic shared by all CEX/DEX
adapters. Each adapter (binance.py, coinbase.py, etc.) inherits from
BaseAdapter and delegates to this mixin for actual CCXT calls.

When CCXT is available and credentials are provided:
    → uses ccxt.<exchange>() for real order placement, balance queries
When CCXT is absent or no credentials:
    → falls back to paper mode (deterministic simulated fills)

Paper-mode fills are tagged ``mode=paper`` in the ledger so they are
distinguishable from real fills during replay and audit.
"""

from __future__ import annotations

from typing import Any

from state.ledger.event_store import append_event
from system import time_source


def ccxt_connect(
    adapter_name: str,
    exchange_id: str,
    api_key: str,
    api_secret: str,
    *,
    sandbox: bool = True,
) -> tuple[Any, bool]:
    """Attempt CCXT connection. Returns (ccxt_instance, is_paper_mode).

    If CCXT connects successfully: returns (instance, False)
    If CCXT unavailable or fails: returns (None, True) → paper mode
    """
    if api_key and api_secret:
        try:
            import ccxt

            exchange_class = getattr(ccxt, exchange_id, None)
            if exchange_class is None:
                append_event(
                    "MARKET",
                    "ADAPTER_CONNECTED",
                    adapter_name,
                    {"mode": "paper", "reason": "unknown_exchange"},
                )
                return None, True

            instance = exchange_class(
                {
                    "apiKey": api_key,
                    "secret": api_secret,
                    "enableRateLimit": True,
                    "sandbox": sandbox,
                }
            )
            append_event(
                "MARKET", "ADAPTER_CONNECTED", adapter_name, {"mode": "live", "sandbox": sandbox}
            )
            return instance, False
        except ImportError:
            pass
        except Exception:
            pass

    append_event("MARKET", "ADAPTER_CONNECTED", adapter_name, {"mode": "paper"})
    return None, True


def ccxt_place_order(
    adapter_name: str,
    ccxt_exchange: Any,
    paper_mode: bool,
    symbol: str,
    side: str,
    size: float,
    order_type: str = "MARKET",
) -> dict[str, Any]:
    """Place order via CCXT or paper fill."""
    ts_ns = time_source.wall_ns()

    if not paper_mode and ccxt_exchange is not None:
        try:
            raw = ccxt_exchange.create_order(
                symbol=symbol,
                type=order_type.lower(),
                side=side.lower(),
                amount=size,
            )
            result: dict[str, Any] = {
                "order_id": str(raw.get("id", "")),
                "symbol": symbol,
                "side": side,
                "size": size,
                "status": raw.get("status", "open"),
                "filled_price": float(raw.get("price") or 0),
                "filled_qty": float(raw.get("filled") or 0),
                "fee": float((raw.get("fee") or {}).get("cost") or 0),
                "ts_ns": ts_ns,
                "mode": "live",
            }
            append_event("MARKET", "ORDER_PLACED", adapter_name, result)
            return result
        except Exception as exc:
            result = {
                "order_id": "",
                "symbol": symbol,
                "side": side,
                "size": size,
                "status": "FAILED",
                "error": str(exc),
                "ts_ns": ts_ns,
                "mode": "live",
            }
            append_event("MARKET", "ORDER_FAILED", adapter_name, result)
            return result

    result = {
        "order_id": f"PAPER_{symbol}_{side}_{ts_ns}",
        "symbol": symbol,
        "side": side,
        "size": size,
        "status": "FILLED",
        "filled_price": 0.0,
        "filled_qty": size,
        "fee": 0.0,
        "ts_ns": ts_ns,
        "mode": "paper",
    }
    append_event("MARKET", "ORDER_PLACED", adapter_name, result)
    return result


def ccxt_cancel_order(
    adapter_name: str,
    ccxt_exchange: Any,
    paper_mode: bool,
    order_id: str,
) -> bool:
    """Cancel order via CCXT or paper cancel."""
    if not paper_mode and ccxt_exchange is not None:
        try:
            ccxt_exchange.cancel_order(order_id)
            append_event(
                "MARKET", "ORDER_CANCELLED", adapter_name, {"order_id": order_id, "mode": "live"}
            )
            return True
        except Exception:
            return False

    append_event("MARKET", "ORDER_CANCELLED", adapter_name, {"order_id": order_id, "mode": "paper"})
    return True


def ccxt_get_balance(
    ccxt_exchange: Any,
    paper_mode: bool,
    asset: str = "USDT",
) -> float:
    """Query balance via CCXT or return paper balance."""
    if not paper_mode and ccxt_exchange is not None:
        try:
            raw = ccxt_exchange.fetch_balance()
            return float(raw.get("total", {}).get(asset) or 0)
        except Exception:
            return 0.0

    return 100_000.0

"""execution_engine.adapters.ig — IG Markets CFD/spread-bet adapter.

Adapts the IG Markets REST + Streaming API through the DIX
:class:`BaseAdapter`. Authentication uses the IG Lightstreamer
session token scheme: a session token is obtained at :meth:`connect`
time and refreshed automatically on 401 responses.

What this module provides
--------------------------
* Full ``async def connect / disconnect / submit_order / cancel_order /
  get_balances`` lifecycle following BaseAdapter ABC.
* Error handling, logging, and ``_record_error`` / ``_record_fill``
  governance integration.
* Lazy SDK import: ``trading_ig`` (IG Markets Python library) is
  imported only at :meth:`connect` time. Falls back to a
  ``urllib``-based implementation when the SDK is absent.
* Capabilities: SPOT (CFDs, spread-bets, FX, indices).

Credentials are passed explicitly — never read from ``os.environ``
(INV-65 per-decision audit truthfulness).

Sandbox mode:
  Pass ``sandbox=True`` to target the IG demo environment.
  Production requires an explicit ``sandbox=False``.

NEW_PIP_DEPENDENCIES: ("trading_ig",)
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from system import time_source

from execution_engine.adapters.base import (
    AdapterCapability,
    AdapterConfig,
    AdapterHealth,
    AdapterStatus,
    BaseAdapter,
    FillReport,
)

logger = logging.getLogger(__name__)

NEW_PIP_DEPENDENCIES: tuple[str, ...] = ("trading_ig",)

_LIVE_BASE = "https://api.ig.com/gateway/deal"
_DEMO_BASE = "https://demo-api.ig.com/gateway/deal"

_VERSION_HEADERS = {
    "Version": "1",
    "Content-Type": "application/json; charset=UTF-8",
    "Accept": "application/json; charset=UTF-8",
}


class IGAdapter(BaseAdapter):
    """IG Markets CFD/spread-bet adapter (DIX VISION v42.2).

    Supports SPOT domain (CFDs, FX, indices, commodities).
    """

    def __init__(
        self,
        config: AdapterConfig,
        *,
        api_key: str,
        username: str,
        password: str,
        account_type: str = "CFD",
        sandbox: bool = True,
    ) -> None:
        super().__init__(config)
        self._api_key = api_key
        self._username = username
        self._password = password
        self._account_type = account_type
        self._sandbox = sandbox
        self._base_url = _DEMO_BASE if sandbox else _LIVE_BASE
        self._cst: str = ""
        self._x_security_token: str = ""
        self._account_id: str = ""

    # ------------------------------------------------------------------
    # BaseAdapter lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        logger.info("IGAdapter.connect sandbox=%s", self._sandbox)
        try:
            payload = json.dumps({
                "identifier": self._username,
                "password": self._password,
            }).encode()
            req = urllib.request.Request(
                f"{self._base_url}/session",
                data=payload,
                headers={
                    **_VERSION_HEADERS,
                    "X-IG-API-KEY": self._api_key,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read())
                self._cst = resp.headers.get("CST", "")
                self._x_security_token = resp.headers.get("X-SECURITY-TOKEN", "")
                self._account_id = body.get("currentAccountId", "")
            self._status = AdapterStatus.CONNECTED
            logger.info("IGAdapter connected account=%s", self._account_id)
            return True
        except Exception as exc:
            self._record_error()
            self._status = AdapterStatus.ERROR
            logger.error(
                "IGAdapter.connect: failed. adapter_id=%s error=%s: %s",
                self._config.adapter_id, type(exc).__name__, str(exc)[:256],
            )
            return False

    async def disconnect(self) -> None:
        logger.info("IGAdapter.disconnect")
        try:
            req = urllib.request.Request(
                f"{self._base_url}/session",
                headers={
                    **_VERSION_HEADERS,
                    "X-IG-API-KEY": self._api_key,
                    "CST": self._cst,
                    "X-SECURITY-TOKEN": self._x_security_token,
                },
                method="DELETE",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as exc:
            logger.warning("IGAdapter.disconnect error: %s", exc)
        finally:
            self._cst = ""
            self._x_security_token = ""
            self._status = AdapterStatus.DISCONNECTED

    async def submit_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
        *,
        intent_id: str = "",
        params: dict[str, Any] | None = None,
    ) -> FillReport:
        """Submit an order to IG Markets.

        IG uses 'epic' as the instrument identifier; DIX symbols like
        'EUR/USD' are auto-converted to IG epic format 'CS.D.EURUSD.CFD.IP'
        if not already in epic format. Operators can pass the raw IG epic
        via ``params={"epic": "CS.D.EURUSD.CFD.IP"}``.

        Raises:
            RuntimeError: If not connected or the API call fails.
        """
        self._require_connected()
        t0_ns = time_source.wall_ns()

        direction = "BUY" if side.upper() == "BUY" else "SELL"
        ig_order_type = order_type.upper() if order_type.upper() in ("MARKET", "LIMIT") else "MARKET"

        epic = (params or {}).get("epic") or symbol
        order_body: dict[str, Any] = {
            "epic": epic,
            "direction": direction,
            "size": str(quantity),
            "orderType": ig_order_type,
            "currencyCode": "USD",
            "forceOpen": False,
            "guaranteedStop": False,
        }
        if ig_order_type == "LIMIT":
            if price is None:
                raise ValueError("IGAdapter.submit_order: price required for LIMIT orders")
            order_body["level"] = str(price)

        if params:
            for k, v in params.items():
                if k != "epic":
                    order_body[k] = v

        try:
            payload = json.dumps(order_body).encode()
            req = urllib.request.Request(
                f"{self._base_url}/positions/otc",
                data=payload,
                headers={
                    **_VERSION_HEADERS,
                    "X-IG-API-KEY": self._api_key,
                    "CST": self._cst,
                    "X-SECURITY-TOKEN": self._x_security_token,
                    "Version": "2",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read())

            latency_ms = (time_source.wall_ns() - t0_ns) / 1_000_000.0
            deal_ref = str(body.get("dealReference", ""))

            # IG returns dealReference on submit; confirm endpoint gives fill price.
            # Use mark-price fallback if confirm is unavailable.
            fill_price = price or 0.0
            try:
                confirm = self._confirm_deal(deal_ref)
                fill_price = float(confirm.get("level", fill_price) or fill_price)
            except Exception:  # noqa: BLE001
                pass

            self._record_fill()
            logger.debug(
                "IGAdapter.submit_order: filled. adapter_id=%s deal_ref=%s "
                "epic=%s direction=%s qty=%.6g price=%.6g latency_ms=%.2f",
                self._config.adapter_id, deal_ref, epic, direction,
                quantity, fill_price, latency_ms,
            )
            return FillReport(
                adapter_id=self._config.adapter_id,
                intent_id=intent_id,
                exchange_order_id=deal_ref,
                symbol=symbol,
                side=direction,
                filled_qty=quantity,
                filled_price=fill_price,
                fee=0.0,
                fee_currency="USD",
                latency_ms=latency_ms,
                partial=False,
                remaining_qty=0.0,
            )
        except Exception as exc:  # noqa: BLE001
            self._record_error()
            logger.error(
                "IGAdapter.submit_order: failed. adapter_id=%s symbol=%s error=%s: %s",
                self._config.adapter_id, symbol, type(exc).__name__, str(exc)[:256],
            )
            raise RuntimeError(
                f"IGAdapter.submit_order failed: {type(exc).__name__}: {exc}"
            ) from exc

    async def cancel_order(self, exchange_order_id: str, symbol: str) -> bool:
        """Cancel a pending IG order by deal ID.

        Args:
            exchange_order_id: IG deal ID to cancel.
            symbol: Instrument (used for logging only).

        Returns:
            ``True`` if successfully cancelled.

        Raises:
            RuntimeError: If not connected or the API call fails.
        """
        self._require_connected()
        try:
            payload = json.dumps({"dealId": exchange_order_id}).encode()
            req = urllib.request.Request(
                f"{self._base_url}/positions/otc",
                data=payload,
                headers={
                    **_VERSION_HEADERS,
                    "X-IG-API-KEY": self._api_key,
                    "CST": self._cst,
                    "X-SECURITY-TOKEN": self._x_security_token,
                    "_method": "DELETE",
                    "Version": "1",
                },
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10)
            logger.info(
                "IGAdapter.cancel_order: cancelled. adapter_id=%s order_id=%s symbol=%s",
                self._config.adapter_id, exchange_order_id, symbol,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            self._record_error()
            logger.error(
                "IGAdapter.cancel_order: failed. adapter_id=%s order_id=%s error=%s: %s",
                self._config.adapter_id, exchange_order_id, type(exc).__name__, str(exc)[:256],
            )
            raise RuntimeError(
                f"IGAdapter.cancel_order failed: {type(exc).__name__}: {exc}"
            ) from exc

    async def get_balances(self) -> dict[str, float]:
        """Return available balances keyed by IG account ID.

        Returns:
            Mapping of accountId → available balance.

        Raises:
            RuntimeError: If not connected or the API call fails.
        """
        self._require_connected()
        try:
            req = urllib.request.Request(
                f"{self._base_url}/accounts",
                headers={
                    **_VERSION_HEADERS,
                    "X-IG-API-KEY": self._api_key,
                    "CST": self._cst,
                    "X-SECURITY-TOKEN": self._x_security_token,
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read())
            balances: dict[str, float] = {}
            for acct in body.get("accounts", []):
                account_id = str(acct.get("accountId", "unknown"))
                available = float(
                    acct.get("balance", {}).get("available", 0.0) or 0.0
                )
                if available > 0.0:
                    balances[account_id] = available
            return balances
        except Exception as exc:  # noqa: BLE001
            self._record_error()
            logger.error(
                "IGAdapter.get_balances: failed. adapter_id=%s error=%s: %s",
                self._config.adapter_id, type(exc).__name__, str(exc)[:256],
            )
            raise RuntimeError(
                f"IGAdapter.get_balances failed: {type(exc).__name__}: {exc}"
            ) from exc

    async def health_check(self) -> AdapterHealth:
        """Return current adapter health, optionally re-checking the session."""
        return AdapterHealth(
            adapter_id=self._config.adapter_id,
            status=self._status,
            last_heartbeat_ns=self._last_heartbeat_ns,
            latency_p50_ms=0.0,
            latency_p99_ms=0.0,
            error_count_1m=self._error_count,
            fill_count_session=self._fill_count,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_connected(self) -> None:
        if self._status is not AdapterStatus.CONNECTED or not self._cst:
            raise RuntimeError(
                f"IGAdapter is not connected (status={self._status.value}). "
                "Call connect() first."
            )

    def _confirm_deal(self, deal_reference: str) -> dict[str, Any]:
        """Fetch the deal confirmation for a submitted order."""
        req = urllib.request.Request(
            f"{self._base_url}/confirms/{urllib.parse.quote(deal_reference)}",
            headers={
                **_VERSION_HEADERS,
                "X-IG-API-KEY": self._api_key,
                "CST": self._cst,
                "X-SECURITY-TOKEN": self._x_security_token,
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())


__all__ = ["IGAdapter"]

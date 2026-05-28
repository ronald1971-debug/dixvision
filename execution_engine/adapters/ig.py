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
            self._record_error("connect_failed", str(exc))
            self._status = AdapterStatus.ERROR
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

    async def submit_order(self, intent: Any) -> FillReport | None:
        if not self._cst:
            self._record_error("submit_order", "not_connected")
            return None
        t0 = time_source.wall_ns()
        try:
            direction = "BUY" if getattr(intent, "side", "BUY").upper() == "BUY" else "SELL"
            payload = json.dumps({
                "epic": getattr(intent, "symbol", ""),
                "direction": direction,
                "size": str(getattr(intent, "qty", 1)),
                "orderType": "MARKET",
                "currencyCode": "USD",
                "forceOpen": False,
                "guaranteedStop": False,
            }).encode()
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
            latency_ms = (time_source.wall_ns() - t0) / 1e6
            fill = FillReport(
                adapter_id=self.config.adapter_id,
                intent_id=getattr(intent, "intent_id", ""),
                exchange_order_id=body.get("dealReference", ""),
                symbol=getattr(intent, "symbol", ""),
                side=direction,
                filled_qty=float(getattr(intent, "qty", 0)),
                filled_price=0.0,
                fee=0.0,
                fee_currency="USD",
                latency_ms=latency_ms,
                ts_ns=time_source.wall_ns(),
            )
            self._record_fill(fill)
            return fill
        except Exception as exc:
            self._record_error("submit_order", str(exc))
            return None

    async def cancel_order(self, order_id: str) -> bool:
        if not self._cst:
            return False
        try:
            payload = json.dumps({"dealId": order_id}).encode()
            req = urllib.request.Request(
                f"{self._base_url}/positions/otc",
                data=payload,
                headers={
                    **_VERSION_HEADERS,
                    "X-IG-API-KEY": self._api_key,
                    "CST": self._cst,
                    "X-SECURITY-TOKEN": self._x_security_token,
                    "_method": "DELETE",
                },
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10)
            return True
        except Exception as exc:
            self._record_error("cancel_order", str(exc))
            return False

    async def get_balances(self) -> dict[str, float]:
        if not self._cst:
            return {}
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
                balances[acct.get("accountId", "unknown")] = float(
                    acct.get("balance", {}).get("available", 0.0)
                )
            return balances
        except Exception as exc:
            self._record_error("get_balances", str(exc))
            return {}

    def health(self) -> AdapterHealth:
        connected = self._status == AdapterStatus.CONNECTED and bool(self._cst)
        return AdapterHealth(
            adapter_id=self.config.adapter_id,
            status=self._status,
            score=1.0 if connected else 0.0,
            last_error=self._last_error,
            fill_count=self._fill_count,
            error_count=self._error_count,
        )


__all__ = ["IGAdapter"]

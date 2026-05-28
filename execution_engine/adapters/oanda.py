"""execution_engine.adapters.oanda — OANDA forex/CFD adapter.

Adapts the OANDA REST v20 API through the DIX :class:`BaseAdapter` so an
approved :class:`ExecutionIntent` becomes a real OANDA forex or CFD order.

What this module provides
--------------------------
* Full ``async def connect / disconnect / submit_order / cancel_order /
  get_balances`` lifecycle following BaseAdapter ABC.
* Error handling, logging, and ``_record_error`` / ``_record_fill``
  governance integration.
* Bearer token authentication: OANDA uses a single API token in the
  ``Authorization: Bearer <token>`` header.
* Capabilities: SPOT (forex pairs, CFDs, indices).
* Handles OANDA instrument format: ``"EUR_USD"`` (underscore separator).

Credentials are passed explicitly — never read from ``os.environ``
(INV-65 per-decision audit truthfulness).

Practice vs live:
  Pass ``practice=True`` (the safe default) to route to the practice
  (paper) environment. Production requires an explicit ``practice=False``.

Practice URL:  https://api-fxpractice.oanda.com
Live URL:      https://api-trade.oanda.com

NEW_PIP_DEPENDENCIES: ()  # stdlib urllib only
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from system import time_source

from execution_engine.adapters.base import (
    AdapterCapability,
    AdapterConfig,
    AdapterStatus,
    BaseAdapter,
    FillReport,
)

logger = logging.getLogger(__name__)

#: No new pip dependencies — uses stdlib urllib.
NEW_PIP_DEPENDENCIES: tuple[str, ...] = ()

#: OANDA v20 REST base URLs.
_PRACTICE_BASE = "https://api-fxpractice.oanda.com"
_LIVE_BASE = "https://api-trade.oanda.com"


class OandaAdapter(BaseAdapter):
    """OANDA REST v20 adapter for forex and CFD markets.

    Declares :attr:`AdapterCapability.SPOT` (OANDA serves forex pairs, CFDs,
    indices, and commodities — all treated as spot instruments in DIX).

    Authentication: Bearer token in ``Authorization`` header.
    Account ID is required separately from the API key (OANDA accounts
    have a numeric account ID, e.g. ``"101-001-12345678-001"``).

    Args:
        config: Standard :class:`AdapterConfig`.
        api_token: OANDA personal access token.
        account_id: OANDA account ID (e.g. ``"101-001-12345678-001"``).
        practice: Route to the practice environment when ``True`` (default).
    """

    exchange: str = "oanda"

    def __init__(
        self,
        config: AdapterConfig,
        *,
        api_token: str = "",
        account_id: str = "",
        practice: bool = True,
    ) -> None:
        super().__init__(config)
        self._api_token = api_token
        self._account_id = account_id
        self._practice = bool(practice)
        self._base_url: str = _PRACTICE_BASE if practice else _LIVE_BASE

    # ------------------------------------------------------------------
    # BaseAdapter lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        """Validate credentials by fetching the OANDA account summary.

        Returns:
            ``True`` if the adapter connected successfully.
        """
        self._status = AdapterStatus.CONNECTING

        if not self._api_token or not self._account_id:
            self._status = AdapterStatus.DISCONNECTED
            logger.warning(
                "OandaAdapter.connect: credentials not wired (api_token/account_id empty). "
                "adapter_id=%s — scaffold mode",
                self.adapter_id,
            )
            return False

        try:
            self._request("GET", f"/v3/accounts/{self._account_id}/summary")
            self._status = AdapterStatus.CONNECTED
            self._last_heartbeat_ns = time_source.wall_ns()
            logger.info(
                "OandaAdapter.connect: connected. adapter_id=%s account=%s practice=%s",
                self.adapter_id, self._account_id, self._practice,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            self._status = AdapterStatus.ERROR
            self._record_error()
            logger.error(
                "OandaAdapter.connect: failed. adapter_id=%s error=%s: %s",
                self.adapter_id, type(exc).__name__, str(exc)[:256],
            )
            return False

    async def disconnect(self) -> None:
        """Gracefully disconnect the adapter."""
        self._status = AdapterStatus.DISCONNECTED
        logger.info("OandaAdapter.disconnect: disconnected. adapter_id=%s", self.adapter_id)

    # ------------------------------------------------------------------
    # Order management
    # ------------------------------------------------------------------

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
        """Submit an order to OANDA.

        OANDA encodes direction in the sign of ``units``: positive = buy,
        negative = sell.

        Args:
            symbol: OANDA instrument name in underscore format (e.g.
                ``"EUR_USD"``). A slash separator (``"EUR/USD"``) is
                auto-converted.
            side: ``"BUY"`` or ``"SELL"``.
            order_type: ``"MARKET"`` or ``"LIMIT"``.
            quantity: Number of units (always positive; direction from ``side``).
            price: Limit price (required for LIMIT orders).
            intent_id: Governance-signed intent ID for tracing (stored in
                OANDA's ``clientExtensions.comment``).
            params: Exchange-specific overrides merged into the order body.

        Returns:
            :class:`FillReport` with execution details.

        Raises:
            RuntimeError: If the adapter is not connected or the API call fails.
        """
        self._require_connected()
        t0_ns = time_source.wall_ns()

        instrument = symbol.replace("/", "_")
        units_signed = quantity if side.upper() == "BUY" else -quantity

        order_body: dict[str, Any] = {
            "type": order_type.upper() if order_type.upper() in ("MARKET", "LIMIT") else "MARKET",
            "instrument": instrument,
            "units": str(units_signed),
            "timeInForce": "FOK" if order_type.upper() == "MARKET" else "GTC",
            "clientExtensions": {
                "comment": intent_id[:128] if intent_id else "",
            },
        }
        if order_type.upper() == "LIMIT":
            if price is None:
                raise ValueError("OandaAdapter.submit_order: price required for LIMIT orders")
            order_body["price"] = str(price)

        if params:
            order_body.update(params)

        payload = {"order": order_body}

        try:
            resp = self._request(
                "POST",
                f"/v3/accounts/{self._account_id}/orders",
                body=payload,
            )

            # Unpack OANDA order fill response.
            fill = resp.get("orderFillTransaction", {})
            order_id = str(fill.get("orderID", resp.get("relatedTransactionIDs", [""])[0]))
            filled_units = abs(float(fill.get("units", units_signed) or units_signed))
            avg_price = float(fill.get("price", price or 0.0) or 0.0)
            fee = abs(float(fill.get("commission", 0.0) or 0.0))

            latency_ms = (time_source.wall_ns() - t0_ns) / 1_000_000.0
            self._record_fill()
            logger.debug(
                "OandaAdapter.submit_order: filled. adapter_id=%s order_id=%s "
                "instrument=%s units=%s price=%.6g latency_ms=%.2f",
                self.adapter_id, order_id, instrument, units_signed, avg_price, latency_ms,
            )
            return FillReport(
                adapter_id=self.adapter_id,
                intent_id=intent_id,
                exchange_order_id=order_id,
                symbol=instrument,
                side=side.upper(),
                filled_qty=filled_units,
                filled_price=avg_price,
                fee=fee,
                fee_currency="USD",
                latency_ms=latency_ms,
                partial=filled_units < quantity,
                remaining_qty=max(quantity - filled_units, 0.0),
            )

        except Exception as exc:  # noqa: BLE001
            self._record_error()
            logger.error(
                "OandaAdapter.submit_order: failed. adapter_id=%s instrument=%s error=%s: %s",
                self.adapter_id, instrument, type(exc).__name__, str(exc)[:256],
            )
            raise RuntimeError(
                f"OandaAdapter.submit_order failed: {type(exc).__name__}: {exc}"
            ) from exc

    async def cancel_order(self, exchange_order_id: str, symbol: str) -> bool:
        """Cancel a pending OANDA order by order ID.

        Args:
            exchange_order_id: OANDA order ID to cancel.
            symbol: Instrument (used for logging only).

        Returns:
            ``True`` if successfully cancelled.

        Raises:
            RuntimeError: If the adapter is not connected or the API call fails.
        """
        self._require_connected()
        try:
            self._request(
                "PUT",
                f"/v3/accounts/{self._account_id}/orders/{exchange_order_id}/cancel",
            )
            logger.info(
                "OandaAdapter.cancel_order: cancelled. adapter_id=%s order_id=%s symbol=%s",
                self.adapter_id, exchange_order_id, symbol,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            self._record_error()
            logger.error(
                "OandaAdapter.cancel_order: failed. adapter_id=%s order_id=%s error=%s: %s",
                self.adapter_id, exchange_order_id, type(exc).__name__, str(exc)[:256],
            )
            raise RuntimeError(
                f"OandaAdapter.cancel_order failed: {type(exc).__name__}: {exc}"
            ) from exc

    async def get_balances(self) -> dict[str, float]:
        """Return account balance as ``{"NAV": <net asset value>}``.

        OANDA accounts are denominated in a base currency (e.g. USD).
        The balance is reported under the account currency key.

        Returns:
            Mapping of currency → balance.

        Raises:
            RuntimeError: If the adapter is not connected or the API call fails.
        """
        self._require_connected()
        try:
            resp = self._request("GET", f"/v3/accounts/{self._account_id}/summary")
            account = resp.get("account", {})
            currency = str(account.get("currency", "USD"))
            balance = float(account.get("balance", 0.0) or 0.0)
            nav = float(account.get("NAV", balance) or balance)
            return {currency: balance, "NAV": nav}
        except Exception as exc:  # noqa: BLE001
            self._record_error()
            logger.error(
                "OandaAdapter.get_balances: failed. adapter_id=%s error=%s: %s",
                self.adapter_id, type(exc).__name__, str(exc)[:256],
            )
            raise RuntimeError(
                f"OandaAdapter.get_balances failed: {type(exc).__name__}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated request to the OANDA v20 REST API.

        Args:
            method: HTTP method (``"GET"``, ``"POST"``, ``"PUT"``).
            path: API path starting with ``/v3/``.
            body: Optional JSON request body.

        Returns:
            Decoded JSON response.

        Raises:
            RuntimeError: On HTTP error or JSON decode failure.
        """
        url = f"{self._base_url}{path}"
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self._api_token}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"OANDA HTTP {exc.code} on {path}: {body_text[:256]}"
            ) from exc

    def _require_connected(self) -> None:
        """Raise RuntimeError if the adapter is not in CONNECTED state."""
        if self._status is not AdapterStatus.CONNECTED:
            raise RuntimeError(
                f"OandaAdapter is not connected (status={self._status.value}). "
                "Call connect() first."
            )


__all__ = [
    "OandaAdapter",
    "NEW_PIP_DEPENDENCIES",
]

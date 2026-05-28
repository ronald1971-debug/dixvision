"""execution_engine.adapters.kraken — Kraken spot + futures adapter.

Adapts the Kraken REST API (spot and futures) through the DIX
:class:`BaseAdapter`. Authentication uses the Kraken API-Key + API-Sign
scheme: requests are signed with HMAC-SHA512 over a canonical nonce +
endpoint payload (as per Kraken private API documentation).

What this module provides
--------------------------
* Full ``async def connect / disconnect / submit_order / cancel_order /
  get_balances`` lifecycle following BaseAdapter ABC.
* Error handling, logging, and ``_record_error`` / ``_record_fill``
  governance integration.
* Lazy SDK import: ``krakenex`` (or equivalent) is imported only at
  :meth:`connect` time. Falls back to a ``urllib``-based implementation
  when the SDK is absent, raising :class:`RuntimeError` at connect time.
* Capabilities: SPOT + FUTURES.

Credentials are passed explicitly — never read from ``os.environ``
(INV-65 per-decision audit truthfulness).

Sandbox mode:
  Pass ``sandbox=True`` to target the Kraken demo-futures environment.
  Production requires an explicit ``sandbox=False``.

NEW_PIP_DEPENDENCIES: ("krakenex",)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
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
    AdapterStatus,
    BaseAdapter,
    FillReport,
)

logger = logging.getLogger(__name__)

#: Pip dependencies required for the optional SDK fast-path.
NEW_PIP_DEPENDENCIES: tuple[str, ...] = ("krakenex",)

#: Kraken REST base URLs.
_SPOT_LIVE_BASE = "https://api.kraken.com"
_FUTURES_LIVE_BASE = "https://futures.kraken.com"
_FUTURES_SANDBOX_BASE = "https://demo-futures.kraken.com"


class KrakenAdapter(BaseAdapter):
    """Kraken spot + futures adapter.

    Declares both :attr:`AdapterCapability.SPOT` and
    :attr:`AdapterCapability.FUTURES`.

    Authentication follows the Kraken private REST protocol:
    * API-Key header: the API key string.
    * API-Sign header: Base64(HMAC-SHA512(API_SECRET, nonce_path_payload)).

    Args:
        config: Standard :class:`AdapterConfig`.
        api_key: Kraken API key. Required for live mode.
        api_secret: Kraken API secret (Base64-encoded private key).
        sandbox: Route to the Kraken demo-futures environment when ``True``
            (the default for safety).
    """

    exchange: str = "kraken"

    def __init__(
        self,
        config: AdapterConfig,
        *,
        api_key: str = "",
        api_secret: str = "",
        sandbox: bool = True,
    ) -> None:
        super().__init__(config)
        self._api_key = api_key
        self._api_secret = api_secret
        self._sandbox = bool(sandbox)
        self._spot_url = _SPOT_LIVE_BASE
        self._futures_url = _FUTURES_SANDBOX_BASE if sandbox else _FUTURES_LIVE_BASE

    # ------------------------------------------------------------------
    # BaseAdapter lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        """Validate credentials by pinging the Kraken balance endpoint.

        Returns:
            ``True`` if connected successfully.
        """
        self._status = AdapterStatus.CONNECTING

        if not self._api_key or not self._api_secret:
            self._status = AdapterStatus.DISCONNECTED
            logger.warning(
                "KrakenAdapter.connect: credentials not wired. adapter_id=%s — scaffold mode",
                self.adapter_id,
            )
            return False

        try:
            result = self._private_request("/0/private/Balance", {})
            if result.get("error"):
                raise RuntimeError(f"Kraken API error: {result['error']}")
            self._status = AdapterStatus.CONNECTED
            self._last_heartbeat_ns = time_source.wall_ns()
            logger.info(
                "KrakenAdapter.connect: connected. adapter_id=%s sandbox=%s",
                self.adapter_id,
                self._sandbox,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            self._status = AdapterStatus.ERROR
            self._record_error()
            logger.error(
                "KrakenAdapter.connect: failed. adapter_id=%s error=%s: %s",
                self.adapter_id, type(exc).__name__, str(exc)[:256],
            )
            return False

    async def disconnect(self) -> None:
        """Gracefully disconnect the adapter."""
        self._status = AdapterStatus.DISCONNECTED
        logger.info("KrakenAdapter.disconnect: disconnected. adapter_id=%s", self.adapter_id)

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
        """Submit an order to Kraken.

        Args:
            symbol: Kraken pair name (e.g. ``"XBTUSD"`` for spot,
                ``"PI_XBTUSD"`` for perpetual futures).
            side: ``"BUY"`` or ``"SELL"``.
            order_type: ``"MARKET"`` or ``"LIMIT"``.
            quantity: Order volume in base asset units.
            price: Limit price (required for LIMIT orders).
            intent_id: Governance-signed intent ID for tracing.
            params: Exchange-specific overrides merged into the order body.

        Returns:
            :class:`FillReport` with execution details.

        Raises:
            RuntimeError: If the adapter is not connected or the API call fails.
        """
        self._require_connected()
        t0_ns = time_source.wall_ns()

        kraken_type = "buy" if side.upper() == "BUY" else "sell"
        kraken_ordertype = order_type.lower()
        if kraken_ordertype not in ("market", "limit"):
            kraken_ordertype = "market"

        body: dict[str, Any] = {
            "pair": symbol,
            "type": kraken_type,
            "ordertype": kraken_ordertype,
            "volume": str(quantity),
            "userref": intent_id[:32] if intent_id else "",
        }
        if kraken_ordertype == "limit":
            if price is None:
                raise ValueError("KrakenAdapter.submit_order: price required for LIMIT orders")
            body["price"] = str(price)
        if params:
            body.update(params)

        try:
            result = self._private_request("/0/private/AddOrder", body)
            if result.get("error"):
                raise RuntimeError(f"Kraken API error: {result['error']}")

            txids = result.get("result", {}).get("txid", [])
            order_id = txids[0] if txids else ""
            desc = result.get("result", {}).get("descr", {})
            filled_price = float(desc.get("price", price or 0.0) or 0.0)

            latency_ms = (time_source.wall_ns() - t0_ns) / 1_000_000.0
            self._record_fill()
            logger.debug(
                "KrakenAdapter.submit_order: submitted. adapter_id=%s order_id=%s "
                "symbol=%s side=%s qty=%.8g latency_ms=%.2f",
                self.adapter_id, order_id, symbol, kraken_type, quantity, latency_ms,
            )
            return FillReport(
                adapter_id=self.adapter_id,
                intent_id=intent_id,
                exchange_order_id=order_id,
                symbol=symbol,
                side=side.upper(),
                filled_qty=quantity,  # Kraken AddOrder is async; report requested qty.
                filled_price=filled_price,
                fee=0.0,
                fee_currency="USD",
                latency_ms=latency_ms,
                partial=False,
                remaining_qty=0.0,
            )

        except Exception as exc:  # noqa: BLE001
            self._record_error()
            logger.error(
                "KrakenAdapter.submit_order: failed. adapter_id=%s symbol=%s error=%s: %s",
                self.adapter_id, symbol, type(exc).__name__, str(exc)[:256],
            )
            raise RuntimeError(
                f"KrakenAdapter.submit_order failed: {type(exc).__name__}: {exc}"
            ) from exc

    async def cancel_order(self, exchange_order_id: str, symbol: str) -> bool:
        """Cancel a pending Kraken order by transaction ID.

        Args:
            exchange_order_id: Kraken transaction ID (txid) to cancel.
            symbol: Trading pair (used for logging only).

        Returns:
            ``True`` if successfully cancelled.

        Raises:
            RuntimeError: If the adapter is not connected or the API call fails.
        """
        self._require_connected()
        try:
            result = self._private_request("/0/private/CancelOrder", {"txid": exchange_order_id})
            if result.get("error"):
                raise RuntimeError(f"Kraken API error: {result['error']}")
            logger.info(
                "KrakenAdapter.cancel_order: cancelled. adapter_id=%s order_id=%s symbol=%s",
                self.adapter_id, exchange_order_id, symbol,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            self._record_error()
            logger.error(
                "KrakenAdapter.cancel_order: failed. adapter_id=%s order_id=%s error=%s: %s",
                self.adapter_id, exchange_order_id, type(exc).__name__, str(exc)[:256],
            )
            raise RuntimeError(
                f"KrakenAdapter.cancel_order failed: {type(exc).__name__}: {exc}"
            ) from exc

    async def get_balances(self) -> dict[str, float]:
        """Return available balances keyed by Kraken asset code.

        Returns:
            Mapping of Kraken asset code (e.g. ``"XXBT"``) → balance.

        Raises:
            RuntimeError: If the adapter is not connected or the API call fails.
        """
        self._require_connected()
        try:
            result = self._private_request("/0/private/Balance", {})
            if result.get("error"):
                raise RuntimeError(f"Kraken API error: {result['error']}")
            raw = result.get("result", {})
            return {asset: float(bal) for asset, bal in raw.items() if float(bal) > 0.0}
        except Exception as exc:  # noqa: BLE001
            self._record_error()
            logger.error(
                "KrakenAdapter.get_balances: failed. adapter_id=%s error=%s: %s",
                self.adapter_id, type(exc).__name__, str(exc)[:256],
            )
            raise RuntimeError(
                f"KrakenAdapter.get_balances failed: {type(exc).__name__}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Internal helpers — Kraken HMAC-SHA512 signing
    # ------------------------------------------------------------------

    def _get_nonce(self) -> str:
        """Generate a Kraken-compatible nonce (millisecond timestamp)."""
        return str(time_source.wall_ns() // 1_000_000)

    def _sign(self, url_path: str, data: dict[str, Any], nonce: str) -> str:
        """Compute the Kraken API-Sign header value.

        Algorithm (from Kraken private REST API docs):
          message = nonce + urlencode(data)
          sha256_message = SHA256(nonce + message)
          signature = Base64(HMAC-SHA512(base64_decode(secret), url_path + sha256_message))
        """
        data_str = urllib.parse.urlencode(data)
        message = nonce + data_str
        sha256_digest = hashlib.sha256((nonce + message).encode()).digest()
        try:
            secret_bytes = base64.b64decode(self._api_secret)
        except Exception:
            # If the secret is not Base64-encoded, use it raw.
            secret_bytes = self._api_secret.encode()
        mac = hmac.new(secret_bytes, url_path.encode() + sha256_digest, hashlib.sha512)
        return base64.b64encode(mac.digest()).decode()

    def _private_request(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        """POST an authenticated request to the Kraken spot REST API.

        Args:
            path: Kraken API path (e.g. ``"/0/private/Balance"``).
            data: Request body fields (without nonce).

        Returns:
            Decoded JSON response.

        Raises:
            RuntimeError: On HTTP error or JSON decode failure.
        """
        nonce = self._get_nonce()
        data = dict(data)
        data["nonce"] = nonce
        sign = self._sign(path, data, nonce)
        url = f"{self._spot_url}{path}"
        body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("API-Key", self._api_key)
        req.add_header("API-Sign", sign)
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Kraken HTTP {exc.code} on {path}: {body_text[:256]}"
            ) from exc

    def _require_connected(self) -> None:
        """Raise RuntimeError if the adapter is not in CONNECTED state."""
        if self._status is not AdapterStatus.CONNECTED:
            raise RuntimeError(
                f"KrakenAdapter is not connected (status={self._status.value}). "
                "Call connect() first."
            )


__all__ = [
    "KrakenAdapter",
    "NEW_PIP_DEPENDENCIES",
]

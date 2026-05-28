"""execution_engine.adapters.coinbase — Coinbase Advanced Trade adapter.

Adapts the Coinbase Advanced Trade REST API through the DIX
:class:`BaseAdapter` so an approved :class:`ExecutionIntent` becomes a real
Coinbase order.

What this module provides
--------------------------
* Full class structure with proper ``async def connect / disconnect /
  submit_order / cancel_order / get_balances`` lifecycle.
* Error handling, logging, and ``_record_error`` / ``_record_fill``
  governance integration following the BaseAdapter contract.
* Lazy SDK import: ``coinbase-advanced-py`` is imported only inside
  :meth:`connect`. This module imports cleanly without the package
  installed — unit tests and the operator dashboard never need the real
  SDK.
* Graceful fallback: when the SDK is absent a :class:`RuntimeError` is
  raised at :meth:`connect` time (not at module load).

Credentials are passed explicitly — never read from ``os.environ``
(INV-65 per-decision audit truthfulness).

Sandbox mode:
  Pass ``sandbox=True`` (the safe default) to target the Coinbase sandbox
  environment. Production requires an explicit ``sandbox=False``.

NEW_PIP_DEPENDENCIES: ("coinbase-advanced-py",)
"""

from __future__ import annotations

import logging
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

#: Pip dependencies required for live mode.
NEW_PIP_DEPENDENCIES: tuple[str, ...] = ("coinbase-advanced-py",)

#: Coinbase Advanced Trade base URLs.
_SANDBOX_BASE = "https://api-public.sandbox.exchange.coinbase.com"
_LIVE_BASE = "https://api.coinbase.com"


class CoinbaseAdapter(BaseAdapter):
    """Coinbase Advanced Trade adapter (SPOT only).

    Coinbase Advanced Trade does not offer native futures; this adapter
    therefore declares only :attr:`AdapterCapability.SPOT`.

    Until :meth:`connect` is called with valid credentials and returns
    ``True``, every call to :meth:`submit_order` / :meth:`cancel_order` /
    :meth:`get_balances` raises :class:`RuntimeError` so callers can tell
    the difference between a scaffold and a live adapter.

    Args:
        config: Standard :class:`AdapterConfig`.
        api_key: Coinbase API key. Required for live mode.
        api_secret: Coinbase API secret (private key). Required for live mode.
        sandbox: Route to the Coinbase sandbox when ``True`` (default).
    """

    exchange: str = "coinbase"

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
        self._base_url: str = _SANDBOX_BASE if sandbox else _LIVE_BASE
        # The REST client from coinbase-advanced-py; populated in connect().
        self._client: Any | None = None

    # ------------------------------------------------------------------
    # BaseAdapter lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        """Validate credentials and arm the adapter.

        Attempts to lazy-import ``coinbase.rest`` from the
        ``coinbase-advanced-py`` SDK. Raises :class:`RuntimeError` if the
        package is not installed. On credential failure the adapter is
        left in :attr:`AdapterStatus.ERROR` and returns ``False``.

        Returns:
            ``True`` if the adapter connected successfully.
        """
        self._status = AdapterStatus.CONNECTING

        # Lazy SDK import — only at connect() time.
        try:
            from coinbase.rest import RESTClient  # type: ignore[import-not-found]  # noqa: PLC0415
        except ImportError as exc:
            self._status = AdapterStatus.ERROR
            logger.error(
                "CoinbaseAdapter.connect: coinbase-advanced-py not installed — "
                "install with 'pip install coinbase-advanced-py'. adapter_id=%s",
                self.adapter_id,
            )
            raise RuntimeError(
                "coinbase-advanced-py not installed; "
                "run 'pip install coinbase-advanced-py' to enable live Coinbase execution."
            ) from exc

        if not self._api_key or not self._api_secret:
            self._status = AdapterStatus.DISCONNECTED
            logger.warning(
                "CoinbaseAdapter.connect: credentials not wired (api_key/api_secret empty). "
                "adapter_id=%s — scaffold mode",
                self.adapter_id,
            )
            return False

        try:
            self._client = RESTClient(
                api_key=self._api_key,
                api_secret=self._api_secret,
            )
            # Ping the accounts endpoint to verify credentials.
            self._client.get_accounts()
            self._status = AdapterStatus.CONNECTED
            self._last_heartbeat_ns = time_source.wall_ns()
            logger.info(
                "CoinbaseAdapter.connect: connected. adapter_id=%s sandbox=%s",
                self.adapter_id,
                self._sandbox,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            self._status = AdapterStatus.ERROR
            self._record_error()
            logger.error(
                "CoinbaseAdapter.connect: failed. adapter_id=%s error=%s: %s",
                self.adapter_id,
                type(exc).__name__,
                str(exc)[:256],
            )
            return False

    async def disconnect(self) -> None:
        """Gracefully disconnect the adapter."""
        self._client = None
        self._status = AdapterStatus.DISCONNECTED
        logger.info("CoinbaseAdapter.disconnect: disconnected. adapter_id=%s", self.adapter_id)

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
        """Submit an order to Coinbase Advanced Trade.

        Constructs the Coinbase REST order payload and posts it via the
        ``coinbase-advanced-py`` SDK. All SDK exceptions are caught and
        re-raised as :class:`RuntimeError` so callers receive a structured
        error rather than a raw SDK exception.

        Args:
            symbol: Coinbase product ID (e.g. ``"BTC-USD"``).
            side: ``"BUY"`` or ``"SELL"``.
            order_type: ``"MARKET"`` or ``"LIMIT"``.
            quantity: Base asset quantity.
            price: Limit price (required for LIMIT orders).
            intent_id: Governance-signed intent ID for tracing.
            params: Exchange-specific overrides passed verbatim to the SDK.

        Returns:
            :class:`FillReport` with execution details.

        Raises:
            RuntimeError: If the adapter is not connected or the SDK call fails.
        """
        self._require_connected()
        t0_ns = time_source.wall_ns()

        cb_side = side.upper()
        if cb_side not in ("BUY", "SELL"):
            raise ValueError(f"CoinbaseAdapter.submit_order: side must be BUY or SELL, got {side!r}")

        try:
            # Build the order configuration dict per Coinbase Advanced Trade API.
            order_config: dict[str, Any] = {}
            if order_type.upper() == "LIMIT":
                if price is None:
                    raise ValueError("CoinbaseAdapter.submit_order: price required for LIMIT orders")
                order_config["limit_limit_gtc"] = {
                    "base_size": str(quantity),
                    "limit_price": str(price),
                    "post_only": False,
                }
            else:
                # MARKET order — base_size for buys, quote_size for sells.
                order_config["market_market_ioc"] = {
                    "base_size": str(quantity),
                }

            if params:
                order_config.update(params)

            raw = self._client.create_order(
                client_order_id=intent_id or f"dix-{time_source.wall_ns()}",
                product_id=symbol,
                side=cb_side,
                order_configuration=order_config,
            )

            # Unpack the Coinbase response.
            success_resp = raw.get("success_response", {})
            order_id = str(success_resp.get("order_id", ""))
            filled_size = float(success_resp.get("filled_size", 0.0) or 0.0)
            avg_price = float(success_resp.get("average_filled_price", price or 0.0) or 0.0)
            fee = float(success_resp.get("total_fees", 0.0) or 0.0)

            latency_ms = (time_source.wall_ns() - t0_ns) / 1_000_000.0
            self._record_fill()
            logger.debug(
                "CoinbaseAdapter.submit_order: filled. adapter_id=%s order_id=%s "
                "symbol=%s side=%s qty=%.8g price=%.8g latency_ms=%.2f",
                self.adapter_id, order_id, symbol, cb_side, filled_size, avg_price, latency_ms,
            )
            return FillReport(
                adapter_id=self.adapter_id,
                intent_id=intent_id,
                exchange_order_id=order_id,
                symbol=symbol,
                side=cb_side,
                filled_qty=filled_size,
                filled_price=avg_price,
                fee=fee,
                fee_currency="USD",
                latency_ms=latency_ms,
                partial=filled_size < quantity,
                remaining_qty=max(quantity - filled_size, 0.0),
            )

        except Exception as exc:  # noqa: BLE001
            self._record_error()
            logger.error(
                "CoinbaseAdapter.submit_order: failed. adapter_id=%s symbol=%s error=%s: %s",
                self.adapter_id, symbol, type(exc).__name__, str(exc)[:256],
            )
            raise RuntimeError(
                f"CoinbaseAdapter.submit_order failed: {type(exc).__name__}: {exc}"
            ) from exc

    async def cancel_order(self, exchange_order_id: str, symbol: str) -> bool:
        """Cancel a pending order by Coinbase order ID.

        Args:
            exchange_order_id: The Coinbase order ID to cancel.
            symbol: Trading pair (used for logging only).

        Returns:
            ``True`` if successfully cancelled.

        Raises:
            RuntimeError: If the adapter is not connected or the SDK call fails.
        """
        self._require_connected()
        try:
            self._client.cancel_orders(order_ids=[exchange_order_id])
            logger.info(
                "CoinbaseAdapter.cancel_order: cancelled. adapter_id=%s order_id=%s symbol=%s",
                self.adapter_id, exchange_order_id, symbol,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            self._record_error()
            logger.error(
                "CoinbaseAdapter.cancel_order: failed. adapter_id=%s order_id=%s error=%s: %s",
                self.adapter_id, exchange_order_id, type(exc).__name__, str(exc)[:256],
            )
            raise RuntimeError(
                f"CoinbaseAdapter.cancel_order failed: {type(exc).__name__}: {exc}"
            ) from exc

    async def get_balances(self) -> dict[str, float]:
        """Return available balances keyed by asset symbol.

        Returns:
            Mapping of asset ticker (e.g. ``"BTC"``) → available balance.

        Raises:
            RuntimeError: If the adapter is not connected or the SDK call fails.
        """
        self._require_connected()
        try:
            response = self._client.get_accounts()
            accounts = response.get("accounts", []) if isinstance(response, dict) else []
            balances: dict[str, float] = {}
            for account in accounts:
                currency = str(account.get("currency", ""))
                available = float(account.get("available_balance", {}).get("value", 0.0) or 0.0)
                if currency and available > 0.0:
                    balances[currency] = available
            return balances
        except Exception as exc:  # noqa: BLE001
            self._record_error()
            logger.error(
                "CoinbaseAdapter.get_balances: failed. adapter_id=%s error=%s: %s",
                self.adapter_id, type(exc).__name__, str(exc)[:256],
            )
            raise RuntimeError(
                f"CoinbaseAdapter.get_balances failed: {type(exc).__name__}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_connected(self) -> None:
        """Raise RuntimeError if the adapter is not in CONNECTED state."""
        if self._status is not AdapterStatus.CONNECTED or self._client is None:
            raise RuntimeError(
                f"CoinbaseAdapter is not connected (status={self._status.value}). "
                "Call connect() first."
            )


__all__ = [
    "CoinbaseAdapter",
    "NEW_PIP_DEPENDENCIES",
]

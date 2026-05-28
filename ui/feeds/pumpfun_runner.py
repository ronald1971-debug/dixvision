"""Background runner for pump.fun launch events via Solana RPC WebSocket (D2).

Replaces the defunct pumpportal.fun WebSocket with a direct Solana RPC
``logsSubscribe`` connection (see :mod:`ui.feeds.solana_launch_ws`).

The public class name ``PumpFunFeedRunner`` is preserved so ``ui/server.py``
and the plugin registry need no changes.

Configuration (env vars):
  SOLANA_WS_URL  — Solana JSON-RPC WebSocket endpoint (default: disabled)
  SOLANA_HTTP_URL — HTTP endpoint for getTransaction calls
    (auto-derived from SOLANA_WS_URL if not set separately)

Recommended free endpoints:
  wss://api.mainnet-beta.solana.com  (public, rate-limited)
  wss://mainnet.helius-rpc.com/?api-key=<key>  (Helius free tier)

INV-15: caller supplies ``clock_ns``; the runner never reads a wall clock.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from collections.abc import Callable

from core.contracts.launches import LaunchEvent
from ui.feeds.solana_launch_ws import (
    DEFAULT_RECONNECT_DELAY_MAX_S,
    DEFAULT_RECONNECT_DELAY_S,
    SolanaLaunchPump,
    SolanaLaunchStatus,
    WSConnect,
)

LOG = logging.getLogger(__name__)

# Opt-in via env var — no default URL, so the feed is disabled until configured.
_ENV_WS_URL = os.environ.get("SOLANA_WS_URL", "").strip()
_ENV_HTTP_URL = os.environ.get("SOLANA_HTTP_URL", "").strip()

# Public alias so callers that type-hint PumpFunStatus still work.
PumpFunStatus = SolanaLaunchStatus


class PumpFunFeedRunner:
    """Owns one asyncio loop + one Solana launch pump, controlled from sync code."""

    def __init__(
        self,
        sink: Callable[[LaunchEvent], None],
        *,
        clock_ns: Callable[[], int],
        connect: WSConnect | None = None,
        url: str = _ENV_WS_URL,
        http_url: str = _ENV_HTTP_URL,
        reconnect_delay_s: float = DEFAULT_RECONNECT_DELAY_S,
        reconnect_delay_max_s: float = DEFAULT_RECONNECT_DELAY_MAX_S,
    ) -> None:
        self._sink = sink
        self._clock_ns = clock_ns
        self._connect = connect
        self._url = url
        self._http_url = http_url
        self._reconnect_delay_s = reconnect_delay_s
        self._reconnect_delay_max_s = reconnect_delay_max_s
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pump: SolanaLaunchPump | None = None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def _provisional_status(self, *, running: bool) -> SolanaLaunchStatus:
        return SolanaLaunchStatus(
            running=running,
            url=self._url,
            last_launch_ts_ns=None,
            launches_received=0,
            errors=0,
        )

    def status(self) -> SolanaLaunchStatus:
        with self._lock:
            pump = self._pump
        if pump is None:
            return self._provisional_status(running=False)
        return pump.status()

    def start(self) -> SolanaLaunchStatus:
        if not self._url:
            LOG.info(
                "pumpfun_ws: no Solana RPC endpoint configured — feed disabled. "
                "Set SOLANA_WS_URL to enable (e.g. wss://api.mainnet-beta.solana.com "
                "or a Helius/QuickNode endpoint)."
            )
            return self._provisional_status(running=False)

        ready = threading.Event()
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                if self._pump is not None:
                    return self._pump.status()
                return self._provisional_status(running=True)

            def _thread_main() -> None:
                loop = asyncio.new_event_loop()
                try:
                    pump = SolanaLaunchPump(
                        self._sink,
                        clock_ns=self._clock_ns,
                        connect=self._connect,
                        url=self._url,
                        http_url=self._http_url,
                        reconnect_delay_s=self._reconnect_delay_s,
                        reconnect_delay_max_s=self._reconnect_delay_max_s,
                    )
                    with self._lock:
                        self._loop = loop
                        self._pump = pump
                    ready.set()
                    loop.run_until_complete(pump.run())
                except Exception:  # noqa: BLE001
                    LOG.exception("pumpfun runner: thread crashed")
                    ready.set()
                finally:
                    try:
                        loop.close()
                    finally:
                        with self._lock:
                            self._loop = None
                            self._pump = None

            thread = threading.Thread(
                target=_thread_main,
                name="pumpfun-feed-runner",
                daemon=True,
            )
            self._thread = thread
            thread.start()

        ready.wait(timeout=5.0)
        return self.status()

    def stop(self) -> SolanaLaunchStatus:
        with self._lock:
            pump = self._pump
            loop = self._loop
            thread = self._thread
        if pump is not None and loop is not None:
            try:
                loop.call_soon_threadsafe(pump.stop)
            except RuntimeError:
                pass
        if thread is not None:
            thread.join(timeout=5.0)
        with self._lock:
            if self._thread is thread and (thread is None or not thread.is_alive()):
                self._thread = None
        return self.status()


__all__ = ["PumpFunFeedRunner", "PumpFunStatus"]

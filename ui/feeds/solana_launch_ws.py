"""Solana RPC WebSocket adapter for pump.fun new-token launches (SRC-LAUNCH-SOLANA-001).

Subscribes to ``logsSubscribe`` on a Solana JSON-RPC WebSocket endpoint
filtered to the pump.fun bonding-curve program ID.  When a ``Create``
instruction is detected the adapter fetches the full transaction via
``getTransaction`` (HTTP JSON-RPC), decodes the Borsh-encoded name /
symbol from the instruction data, and emits a :class:`LaunchEvent`.

Default endpoints (public, rate-limited — suitable for dev / testing):
  WS:   wss://api.mainnet-beta.solana.com
  HTTP: https://api.mainnet-beta.solana.com

For production, supply a Helius or QuickNode endpoint via env vars:
  SOLANA_WS_URL  — WebSocket subscription endpoint
  SOLANA_HTTP_URL — HTTP endpoint for ``getTransaction`` calls
    (derived automatically from SOLANA_WS_URL if not set separately)

INV-15: ``clock_ns`` is supplied by the caller; the pump never reads the
wall clock internally, so replays with the same inputs are deterministic.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from core.contracts.launches import LaunchEvent

LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: pump.fun bonding-curve program address (mainnet).
PUMPFUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

#: Public Solana mainnet-beta RPC endpoints (free, rate-limited).
DEFAULT_WS_URL = "wss://api.mainnet-beta.solana.com"
DEFAULT_HTTP_URL = "https://api.mainnet-beta.solana.com"

DEFAULT_RECONNECT_DELAY_S = 5.0
DEFAULT_RECONNECT_DELAY_MAX_S = 120.0
DEFAULT_FETCH_RETRIES = 3
DEFAULT_FETCH_RETRY_DELAY_S = 0.5

VENUE_TAG = "PUMPFUN"
CHAIN_TAG = "solana"

# ---------------------------------------------------------------------------
# Base58 encode / decode (no external dependency)
# ---------------------------------------------------------------------------

_B58_ALPHA = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_MAP: dict[str, int] = {c: i for i, c in enumerate(_B58_ALPHA)}


def _b58encode(data: bytes) -> str:
    """Encode bytes to base58 (for Solana public key display)."""
    n_pad = 0
    for b in data:
        if b == 0:
            n_pad += 1
        else:
            break
    n = int.from_bytes(data, "big")
    chars: list[str] = []
    while n:
        n, rem = divmod(n, 58)
        chars.append(_B58_ALPHA[rem])
    return "1" * n_pad + "".join(reversed(chars))


def _b58decode(s: str) -> bytes:
    """Decode a base58 string to bytes."""
    n_pad = 0
    for c in s:
        if c == "1":
            n_pad += 1
        else:
            break
    n = 0
    for c in s:
        v = _B58_MAP.get(c)
        if v is None:
            raise ValueError(f"Invalid base58 character: {c!r}")
        n = n * 58 + v
    result: list[int] = []
    while n:
        n, rem = divmod(n, 256)
        result.append(rem)
    return bytes(n_pad) + bytes(reversed(result))


# ---------------------------------------------------------------------------
# Borsh decoder (subset — strings only)
# ---------------------------------------------------------------------------


def _read_borsh_string(data: bytes, offset: int) -> tuple[str, int]:
    """Read a Borsh-encoded string: u32-LE length prefix + UTF-8 payload."""
    if offset + 4 > len(data):
        raise ValueError(f"buffer too short for length prefix at offset {offset}")
    length = int.from_bytes(data[offset : offset + 4], "little")
    offset += 4
    if offset + length > len(data):
        raise ValueError(
            f"string of length {length} extends past buffer end {len(data)}"
        )
    return data[offset : offset + length].decode("utf-8", errors="replace"), offset + length


def decode_create_instruction(data_b58: str) -> tuple[str, str, str] | None:
    """Decode ``(name, symbol, uri)`` from a pump.fun Create instruction payload.

    The payload is base58-encoded.  The first 8 bytes are the Anchor
    instruction discriminator (``sha256("global:create")[:8]``); the
    remainder is Borsh-encoded: name (String), symbol (String), uri (String), …

    Returns ``None`` on any parse failure so callers can skip silently.
    """
    try:
        raw = _b58decode(data_b58)
        offset = 8  # skip Anchor discriminator
        name, offset = _read_borsh_string(raw, offset)
        symbol, offset = _read_borsh_string(raw, offset)
        uri, offset = _read_borsh_string(raw, offset)
        return name, symbol, uri
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Log-level Create detection
# ---------------------------------------------------------------------------


def _has_pumpfun_create(logs: list[str], program_id: str) -> bool:
    """Return True if logs show pump.fun executing a top-level Create instruction.

    Scans for ``"Instruction: Create"`` appearing *inside* the program's
    invocation scope (between its invoke and success/failed lines) to avoid
    false positives from other programs in the same transaction.
    """
    invoke_marker = f"Program {program_id} invoke"
    close_marker = f"Program {program_id} "  # "… success" or "… failed"
    inside = False
    for line in logs:
        if line.startswith(invoke_marker):
            inside = True
        elif inside and "Instruction: Create" in line:
            return True
        elif inside and line.startswith(close_marker) and not line.startswith(invoke_marker):
            inside = False
    return False


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def _ws_url_to_http(ws_url: str) -> str:
    """Derive the HTTP RPC URL from a WebSocket URL."""
    if ws_url.startswith("wss://"):
        return "https://" + ws_url[6:]
    if ws_url.startswith("ws://"):
        return "http://" + ws_url[5:]
    return ws_url


# ---------------------------------------------------------------------------
# WebSocket connection protocol
# ---------------------------------------------------------------------------


class _WSConn(Protocol):
    async def send(self, message: str) -> None: ...  # pragma: no cover
    def __aiter__(self) -> Any: ...  # pragma: no cover
    async def close(self) -> None: ...  # pragma: no cover


WSConnect = Callable[[str], Awaitable[_WSConn]]


async def _default_ws_connect(url: str) -> _WSConn:
    import websockets  # local import — heavy dependency

    return await websockets.connect(  # type: ignore[return-value]
        url,
        user_agent_header="Mozilla/5.0 (compatible; DIXVision/42)",
    )


# ---------------------------------------------------------------------------
# Status snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SolanaLaunchStatus:
    """Health snapshot for the Solana launch feed (mirrors PumpFunStatus API)."""

    running: bool
    url: str
    last_launch_ts_ns: int | None
    launches_received: int
    errors: int


# ---------------------------------------------------------------------------
# Main pump
# ---------------------------------------------------------------------------

_HTTP_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "DIXVision/42",
}


class SolanaLaunchPump:
    """Async pump: Solana RPC ``logsSubscribe`` → pump.fun ``LaunchEvent`` sink.

    Flow per new-token transaction:

    1. Receives a ``logsNotification`` from the WS subscription.
    2. Fast-filters: skips failed transactions and non-Create invocations.
    3. Calls ``getTransaction`` (HTTP) to fetch full instruction data.
    4. Borsh-decodes ``(name, symbol, uri)`` from the Create instruction.
    5. Extracts ``mint`` and ``creator`` from the transaction account list.
    6. Emits a :class:`LaunchEvent` into the caller-supplied sink.

    ``getTransaction`` calls run as concurrent asyncio tasks so a slow RPC
    response does not stall the WebSocket receive loop.
    """

    def __init__(
        self,
        sink: Callable[[LaunchEvent], None],
        *,
        clock_ns: Callable[[], int],
        connect: WSConnect | None = None,
        url: str = DEFAULT_WS_URL,
        http_url: str = "",
        program_id: str = PUMPFUN_PROGRAM_ID,
        reconnect_delay_s: float = DEFAULT_RECONNECT_DELAY_S,
        reconnect_delay_max_s: float = DEFAULT_RECONNECT_DELAY_MAX_S,
        fetch_retries: int = DEFAULT_FETCH_RETRIES,
        fetch_retry_delay_s: float = DEFAULT_FETCH_RETRY_DELAY_S,
        venue: str = VENUE_TAG,
        chain: str = CHAIN_TAG,
    ) -> None:
        if not url:
            raise ValueError("SolanaLaunchPump: url required")
        if reconnect_delay_s <= 0:
            raise ValueError("SolanaLaunchPump: reconnect_delay_s must be positive")
        if reconnect_delay_max_s < reconnect_delay_s:
            raise ValueError("SolanaLaunchPump: reconnect_delay_max_s must be >= reconnect_delay_s")

        self._sink = sink
        self._clock_ns = clock_ns
        self._connect: WSConnect = connect if connect is not None else _default_ws_connect
        self._url = url
        self._http_url = http_url or _ws_url_to_http(url)
        self._program_id = program_id
        self._reconnect_delay_s = reconnect_delay_s
        self._reconnect_delay_max_s = reconnect_delay_max_s
        self._fetch_retries = fetch_retries
        self._fetch_retry_delay_s = fetch_retry_delay_s
        self._venue = venue
        self._chain = chain

        self._subscribe_frame = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "logsSubscribe",
                "params": [
                    {"mentions": [program_id]},
                    {"commitment": "confirmed"},
                ],
            },
            separators=(",", ":"),
        )

        self._stop_event = asyncio.Event()
        self._launches_received = 0
        self._errors = 0
        self._last_launch_ts_ns: int | None = None
        self._running = False
        self._consecutive_errors = 0

    @property
    def url(self) -> str:
        return self._url

    def status(self) -> SolanaLaunchStatus:
        return SolanaLaunchStatus(
            running=self._running,
            url=self._url,
            last_launch_ts_ns=self._last_launch_ts_ns,
            launches_received=self._launches_received,
            errors=self._errors,
        )

    def stop(self) -> None:
        self._stop_event.set()

    async def run(self) -> None:
        """Connect → subscribe → consume until ``stop()``, with exponential backoff."""
        self._running = True
        delay = self._reconnect_delay_s
        client = httpx.AsyncClient(headers=_HTTP_HEADERS, timeout=10.0)
        try:
            while not self._stop_event.is_set():
                conn: _WSConn | None = None
                pending: set[asyncio.Task[None]] = set()
                try:
                    conn = await self._connect(self._url)
                    await conn.send(self._subscribe_frame)
                    LOG.info(
                        "solana_launch_ws: subscribed url=%s program=%s",
                        self._url,
                        self._program_id,
                    )
                    delay = self._reconnect_delay_s
                    self._consecutive_errors = 0

                    async for raw in conn:  # type: ignore[union-attr]
                        if self._stop_event.is_set():
                            break
                        task: asyncio.Task[None] = asyncio.create_task(
                            self._handle_notification(raw, client)
                        )
                        pending.add(task)
                        task.add_done_callback(pending.discard)

                except Exception as exc:  # noqa: BLE001
                    self._errors += 1
                    self._consecutive_errors += 1
                    _http_status = getattr(
                        getattr(exc, "response", None), "status_code", None
                    )
                    if _http_status == 403:
                        LOG.warning(
                            "solana_launch_ws: HTTP 403 — check SOLANA_WS_URL "
                            "credentials or endpoint URL. Feed disabled."
                        )
                        break
                    if self._consecutive_errors == 1:
                        LOG.exception(
                            "solana_launch_ws: connection failure; reconnect in %.1fs",
                            delay,
                        )
                    elif self._consecutive_errors == 5:
                        LOG.warning(
                            "solana_launch_ws: %d consecutive failures; "
                            "further errors suppressed until reconnected (delay=%.1fs)",
                            self._consecutive_errors,
                            delay,
                        )
                    else:
                        LOG.debug(
                            "solana_launch_ws: failure #%d; reconnect in %.1fs",
                            self._consecutive_errors,
                            delay,
                        )
                finally:
                    for t in list(pending):
                        t.cancel()
                    if conn is not None:
                        try:
                            await conn.close()
                        except Exception:  # noqa: BLE001
                            pass

                if self._stop_event.is_set():
                    break
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                except TimeoutError:
                    pass
                delay = min(delay * 2.0, self._reconnect_delay_max_s)
        finally:
            self._running = False
            try:
                await client.aclose()
            except Exception:  # noqa: BLE001
                pass

    async def _handle_notification(
        self, raw: str | bytes, client: httpx.AsyncClient
    ) -> None:
        """Parse one WS frame; fetch + emit LaunchEvent if it is a Create tx."""
        try:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            msg = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return

        if msg.get("method") != "logsNotification":
            return

        value: dict[str, Any] = (
            (msg.get("params") or {}).get("result") or {}
        ).get("value") or {}

        # Skip failed transactions immediately.
        if value.get("err") is not None:
            return

        logs: list[str] = value.get("logs") or []
        if not _has_pumpfun_create(logs, self._program_id):
            return

        signature: str = value.get("signature") or ""
        if not signature:
            return

        ts_ns = self._clock_ns()
        tx_result = await self._get_transaction(signature, client)
        if tx_result is None:
            self._errors += 1
            LOG.debug("solana_launch_ws: getTransaction null for %s", signature)
            return

        event = self._extract_launch_event(tx_result, ts_ns, signature)
        if event is None:
            return

        try:
            self._sink(event)
        except Exception:  # noqa: BLE001
            self._errors += 1
            LOG.exception("solana_launch_ws: sink raised on event=%r", event)
            return

        self._launches_received += 1
        self._last_launch_ts_ns = ts_ns

    async def _get_transaction(
        self, signature: str, client: httpx.AsyncClient
    ) -> dict[str, Any] | None:
        """Fetch a confirmed transaction from the HTTP RPC, with retries."""
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "getTransaction",
                "params": [
                    signature,
                    {
                        "encoding": "json",
                        "commitment": "confirmed",
                        "maxSupportedTransactionVersion": 0,
                    },
                ],
            },
            separators=(",", ":"),
        )
        for attempt in range(self._fetch_retries):
            try:
                resp = await client.post(self._http_url, content=payload)
                if resp.status_code != 200:
                    return None
                data = resp.json()
                result = data.get("result")
                if result is not None:
                    return result
                # null = not yet propagated; short wait then retry
                if attempt < self._fetch_retries - 1:
                    await asyncio.sleep(self._fetch_retry_delay_s)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                if attempt < self._fetch_retries - 1:
                    await asyncio.sleep(self._fetch_retry_delay_s)
        return None

    def _extract_launch_event(
        self,
        tx_result: dict[str, Any],
        ts_ns: int,
        signature: str,
    ) -> LaunchEvent | None:
        """Build a LaunchEvent from a parsed ``getTransaction`` result."""
        try:
            tx = tx_result.get("transaction") or {}
            msg_block = tx.get("message") or {}

            # For v0 transactions, static keys + loaded addresses = full account list.
            account_keys: list[str] = list(msg_block.get("accountKeys") or [])
            meta = tx_result.get("meta") or {}
            loaded = meta.get("loadedAddresses") or {}
            account_keys.extend(loaded.get("writable") or [])
            account_keys.extend(loaded.get("readonly") or [])

            if not account_keys:
                return None

            # Locate pump.fun program in account list.
            try:
                prog_idx = account_keys.index(self._program_id)
            except ValueError:
                return None

            # Find the Create instruction for the pump.fun program.
            instructions: list[dict[str, Any]] = msg_block.get("instructions") or []
            create_ix: dict[str, Any] | None = None
            for ix in instructions:
                if ix.get("programIdIndex") == prog_idx:
                    create_ix = ix
                    break
            if create_ix is None:
                return None

            ix_accounts: list[int] = create_ix.get("accounts") or []
            ix_data_b58: str = create_ix.get("data") or ""
            if not ix_data_b58:
                return None

            decoded = decode_create_instruction(ix_data_b58)
            if decoded is None:
                LOG.debug("solana_launch_ws: Borsh decode failed for tx %s", signature)
                return None
            name, symbol, _uri = decoded

            # mint = instruction accounts[0]; creator = accounts[7] or fee payer.
            mint = account_keys[ix_accounts[0]] if ix_accounts else ""
            if len(ix_accounts) >= 8:
                creator = account_keys[ix_accounts[7]]
            else:
                creator = account_keys[0] if account_keys else ""

            slot = tx_result.get("slot")
            return LaunchEvent(
                ts_ns=ts_ns,
                chain=self._chain,
                venue=self._venue,
                mint=mint,
                symbol=symbol,
                name=name,
                creator=creator,
                market_cap_usd=0.0,
                liquidity_usd=0.0,
                meta={"signature": signature, "slot": str(slot) if slot else ""},
            )
        except (KeyError, IndexError, TypeError):
            return None


__all__ = [
    "CHAIN_TAG",
    "DEFAULT_FETCH_RETRIES",
    "DEFAULT_FETCH_RETRY_DELAY_S",
    "DEFAULT_HTTP_URL",
    "DEFAULT_RECONNECT_DELAY_MAX_S",
    "DEFAULT_RECONNECT_DELAY_S",
    "DEFAULT_WS_URL",
    "PUMPFUN_PROGRAM_ID",
    "SolanaLaunchPump",
    "SolanaLaunchStatus",
    "VENUE_TAG",
    "WSConnect",
    "decode_create_instruction",
]

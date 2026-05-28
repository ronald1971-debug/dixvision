"""Cognitive stream projection routes (COGNITIVE ACTIVATION PHASE).

SSE endpoint and snapshot REST endpoint serving the two cognitive
intelligence streams to the operator dashboard in real time:

  GET /api/cognitive/stream    — Server-Sent Events (text/event-stream)
  GET /api/cognitive/snapshot  — JSON snapshot of the last N events

INTELLIGENCE/INDIRA stream → SSE channel "indira"
SYSTEM/DYON stream         → SSE channel "dyon"

Wire format mirrors the existing /api/dashboard/stream contract:
  data: {"channel": "indira"|"dyon", "ts_iso": "<iso>", "payload": {...}}

The operator connects here to see both intelligences evolve in real time
(Executive Directive: Operator Sovereignty P2 — operator must always
have visibility into both INDIRA and DYON cognitive activity).

This module never imports *_engine packages directly. All ledger access
goes through the EventStore supplier injected at construction time.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from system.time_source import utc_now


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------


def _ts_iso(row: dict[str, Any]) -> str:
    ts = row.get("timestamp_utc")
    if ts:
        return str(ts)
    return utc_now().isoformat()


def _parse_payload(row: dict[str, Any]) -> dict[str, Any]:
    """Return row with payload JSON string decoded to dict."""
    out = dict(row)
    raw = out.get("payload")
    if isinstance(raw, str):
        try:
            out["payload"] = json.loads(raw)
        except (ValueError, TypeError):
            pass
    return out


def _format_sse(channel: str, row: dict[str, Any]) -> bytes:
    event = {
        "channel": channel,
        "ts_iso": _ts_iso(row),
        "payload": _parse_payload(row),
    }
    return f"data: {json.dumps(event, separators=(',', ':'), default=str)}\n\n".encode("utf-8")


# ---------------------------------------------------------------------------
# Async SSE generator
# ---------------------------------------------------------------------------


async def _cognitive_sse_generator(
    request: Request,
    *,
    event_store_supplier: Callable[[], Any],
    backfill_n: int = 50,
    poll_interval_s: float = 0.5,
    keepalive_every_s: float = 15.0,
) -> AsyncIterator[bytes]:
    """Yield SSE bytes for INTELLIGENCE/INDIRA and SYSTEM/DYON streams.

    Phase 1 (backfill): emit the last ``backfill_n`` events from each
    stream, interleaved in id order so the operator sees a chronological
    history on connect.

    Phase 2 (tail): poll for new events every ``poll_interval_s`` seconds
    using ``query_since(last_id)`` — only new rows are emitted so the
    stream is low-CPU when both intelligences are quiet.

    Keepalives are sent every ``keepalive_every_s`` to prevent reverse-
    proxy / browser timeouts.
    """
    yield b": connected\n\n"

    store = event_store_supplier()

    # Phase 1 — backfill: newest-first from query(), reversed for chrono order
    indira_backfill = list(reversed(
        store.query(event_type="INTELLIGENCE", source="INDIRA", limit=backfill_n)
    ))
    dyon_backfill = list(reversed(
        store.query(event_type="SYSTEM", source="DYON", limit=backfill_n)
    ))

    # Merge both backlogs in id order for a coherent timeline
    combined_backfill = (
        [("indira", r) for r in indira_backfill]
        + [("dyon", r) for r in dyon_backfill]
    )
    combined_backfill.sort(key=lambda t: t[1].get("id", 0))

    last_id = 0
    for channel, row in combined_backfill:
        row_id = row.get("id", 0)
        if isinstance(row_id, int):
            last_id = max(last_id, row_id)
        yield _format_sse(channel, row)

    # Phase 2 — tail loop
    last_keepalive = asyncio.get_event_loop().time()
    try:
        while True:
            if await request.is_disconnected():
                return

            store = event_store_supplier()
            new_indira = store.query_since(last_id, event_type="INTELLIGENCE", source="INDIRA")
            new_dyon = store.query_since(last_id, event_type="SYSTEM", source="DYON")

            combined = (
                [("indira", r) for r in new_indira]
                + [("dyon", r) for r in new_dyon]
            )
            combined.sort(key=lambda t: t[1].get("id", 0))

            for channel, row in combined:
                row_id = row.get("id", 0)
                if isinstance(row_id, int):
                    last_id = max(last_id, row_id)
                yield _format_sse(channel, row)

            now_loop = asyncio.get_event_loop().time()
            if now_loop - last_keepalive >= keepalive_every_s:
                yield b": keepalive\n\n"
                last_keepalive = now_loop

            await asyncio.sleep(poll_interval_s)
    except asyncio.CancelledError:
        return


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


def build_cognitive_stream_router(
    event_store_supplier: Callable[[], Any] | None = None,
) -> APIRouter:
    """Construct the cognitive stream router.

    Args:
        event_store_supplier: Zero-arg callable returning an EventStore.
            Defaults to the module-level get_event_store() singleton.
            Injected for testability.
    """
    if event_store_supplier is None:
        from state.ledger.event_store import get_event_store
        event_store_supplier = get_event_store

    router = APIRouter(prefix="/api/cognitive", tags=["cognitive-stream"])

    @router.get("/stream")
    async def cognitive_stream(
        request: Request,
        backfill_n: int = 50,
    ) -> StreamingResponse:
        """SSE stream for the two cognitive intelligence surfaces.

        Connect here to observe both INDIRA (market intelligence) and
        DYON (engineering intelligence) evolving in real time.

        Events arrive as:
          data: {"channel": "indira"|"dyon", "ts_iso": "...", "payload": {...}}

        Query params:
          backfill_n — number of historical events per stream on connect (default 50, max 500)
        """
        return StreamingResponse(
            _cognitive_sse_generator(
                request,
                event_store_supplier=event_store_supplier,
                backfill_n=max(0, min(backfill_n, 500)),
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @router.get("/snapshot")
    def cognitive_snapshot(limit: int = 50) -> dict[str, Any]:
        """JSON snapshot of recent events from both cognitive streams.

        Returns newest-first within each stream. Use for initial dashboard
        load before the SSE connection is established.

        Query params:
          limit — max events per stream (default 50, max 500)
        """
        n = max(1, min(limit, 500))
        store = event_store_supplier()
        return {
            "indira": [
                _parse_payload(r)
                for r in store.query(event_type="INTELLIGENCE", source="INDIRA", limit=n)
            ],
            "dyon": [
                _parse_payload(r)
                for r in store.query(event_type="SYSTEM", source="DYON", limit=n)
            ],
        }

    return router


__all__ = ["build_cognitive_stream_router"]

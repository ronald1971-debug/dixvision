"""ui.memory_routes — REST endpoints for the Unified Cognitive Memory Layer.

Surfaces:
  GET /api/memory/snapshot         — full UnifiedMemoryLayer snapshot
  GET /api/memory/timeline         — CognitionTimeline entries (paginated)
  GET /api/memory/search           — cross-store keyword search
  GET /api/memory/identity         — MemoryIdentitySystem stats
  GET /api/memory/compression      — MemoryCompressor stats
  GET /api/memory/replay/sessions  — active/completed replay sessions
  POST /api/memory/replay/start    — start a new replay session
  GET /api/memory/stores/strategy  — StrategyMemoryStore snapshot + recent
  GET /api/memory/stores/trader    — TraderMemoryStore snapshot + leaderboard
  GET /api/memory/stores/governance — GovernanceMemoryStore snapshot + recent
  GET /api/memory/stores/runtime   — RuntimeEventMemoryStore snapshot + recent
"""

from __future__ import annotations

import logging
import time

_logger = logging.getLogger(__name__)


def build_memory_router():
    try:
        from fastapi import APIRouter, Query
        from fastapi.responses import JSONResponse
    except ImportError:
        return None

    router = APIRouter()

    # ── snapshot ───────────────────────────────────────────────────────

    @router.get("/api/memory/snapshot")
    async def memory_snapshot():
        try:
            from state.memory.unified import get_unified_memory_layer
            return get_unified_memory_layer().snapshot()
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    # ── timeline ───────────────────────────────────────────────────────

    @router.get("/api/memory/timeline")
    async def memory_timeline(
        limit:    int    = Query(50,  ge=1, le=500),
        since_ns: int    = Query(0,   ge=0),
        kind:     str    = Query("",  description="Comma-separated MemoryKind values"),
    ):
        try:
            from state.memory.timeline import get_cognition_timeline
            kinds = [k.strip().upper() for k in kind.split(",") if k.strip()] or None
            tl    = get_cognition_timeline()
            rows  = tl.query(
                since_ns=since_ns or None,
                kinds=kinds,
                limit=limit,
            )
            return {"count": len(rows), "records": rows, "persisted": tl.count()}
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    # ── search ─────────────────────────────────────────────────────────

    @router.get("/api/memory/search")
    async def memory_search(
        q:     str = Query(..., description="Space-separated keywords"),
        limit: int = Query(20, ge=1, le=200),
        mode:  str = Query("all", description="'all' (AND) or 'any' (OR)"),
    ):
        try:
            from state.memory.index import get_memory_index
            idx      = get_memory_index()
            keywords = q.split()
            records  = (
                idx.search(keywords, limit=limit)
                if mode == "all"
                else idx.search_any(keywords, limit=limit)
            )
            return {
                "query":    q,
                "mode":     mode,
                "count":    len(records),
                "records":  [
                    {
                        "record_id":  r.record_id,
                        "kind":       r.kind.value,
                        "ts_ns":      r.ts_ns,
                        "source":     r.source,
                        "summary":    r.summary,
                        "tags":       sorted(r.tags),
                        "confidence": r.confidence,
                    }
                    for r in records
                ],
            }
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    # ── identity ───────────────────────────────────────────────────────

    @router.get("/api/memory/identity")
    async def memory_identity():
        try:
            from state.memory.identity import get_memory_identity_system
            return get_memory_identity_system().snapshot()
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    # ── compression ────────────────────────────────────────────────────

    @router.get("/api/memory/compression")
    async def memory_compression():
        try:
            from state.memory.compression import get_memory_compressor
            return get_memory_compressor().snapshot()
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    # ── replay ─────────────────────────────────────────────────────────

    @router.get("/api/memory/replay/sessions")
    async def memory_replay_sessions():
        try:
            from state.memory.replay import get_memory_replay_engine
            eng = get_memory_replay_engine()
            return {"sessions": eng.list_sessions(), **eng.snapshot()}
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    @router.post("/api/memory/replay/start")
    async def memory_replay_start(
        session_id: str = Query(...),
        since_ns:   int = Query(...,  ge=1),
        until_ns:   int = Query(0,   ge=0, description="0 = now"),
        kind:       str = Query("",  description="Comma-separated MemoryKind values"),
    ):
        try:
            from state.memory.replay import get_memory_replay_engine
            eng      = get_memory_replay_engine()
            kinds    = [k.strip().upper() for k in kind.split(",") if k.strip()] or None
            until    = until_ns or time.time_ns()
            session  = eng.start_replay(
                session_id=session_id,
                since_ns=since_ns,
                until_ns=until,
                kinds=kinds,
            )
            return {
                "session_id": session.session_id,
                "since_ns":   session.since_ns,
                "until_ns":   session.until_ns,
                "status":     "started",
            }
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    # ── domain stores ──────────────────────────────────────────────────

    @router.get("/api/memory/stores/strategy")
    async def memory_store_strategy(limit: int = Query(20, ge=1, le=200)):
        try:
            from state.memory.stores.strategy import get_strategy_memory_store
            store = get_strategy_memory_store()
            snap  = store.snapshot()
            snap["recent"] = [
                {"record_id": r.record_id, "summary": r.summary, "ts_ns": r.ts_ns}
                for r in store.recent(limit)
            ]
            return snap
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    @router.get("/api/memory/stores/trader")
    async def memory_store_trader(
        limit:  int = Query(20,  ge=1, le=200),
        regime: str = Query("", description="Filter leaderboard by regime"),
    ):
        try:
            from state.memory.stores.trader import get_trader_memory_store
            store = get_trader_memory_store()
            snap  = store.snapshot()
            snap["leaderboard"] = store.leaderboard(regime=regime or None)
            snap["recent"] = [
                {"record_id": r.record_id, "summary": r.summary, "ts_ns": r.ts_ns}
                for r in store.recent(limit)
            ]
            return snap
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    @router.get("/api/memory/stores/governance")
    async def memory_store_governance(limit: int = Query(20, ge=1, le=200)):
        try:
            from state.memory.stores.governance import get_governance_memory_store
            store = get_governance_memory_store()
            snap  = store.snapshot()
            snap["mode_history"] = store.mode_history(limit=10)
            snap["recent"] = [
                {"record_id": r.record_id, "summary": r.summary, "ts_ns": r.ts_ns}
                for r in store.recent(limit)
            ]
            return snap
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    @router.get("/api/memory/stores/runtime")
    async def memory_store_runtime(limit: int = Query(20, ge=1, le=200)):
        try:
            from state.memory.stores.runtime_events import get_runtime_event_memory_store
            store = get_runtime_event_memory_store()
            snap  = store.snapshot()
            snap["recent"] = [
                {"record_id": r.record_id, "summary": r.summary, "ts_ns": r.ts_ns}
                for r in store.recent(limit)
            ]
            return snap
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    return router


__all__ = ["build_memory_router"]

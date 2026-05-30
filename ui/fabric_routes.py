"""ui.fabric_routes — REST endpoints for the Unified Event Fabric.

Surfaces:
  GET  /api/fabric/snapshot           — full UnifiedEventFabric snapshot
  GET  /api/fabric/authority          — CentralBusAuthority stats
  GET  /api/fabric/tracing            — EventTracer: recent spans
  GET  /api/fabric/tracing/{trace_id} — full trace tree by trace_id
  GET  /api/fabric/lineage            — EventLineageGraph: recent causal links
  GET  /api/fabric/lineage/{event_id} — root cause chain for event
  GET  /api/fabric/persistence        — FabricPersistence stats + domain counts
  GET  /api/fabric/replay             — replay stream: list sessions
  POST /api/fabric/replay/start       — start a new replay session
  GET  /api/fabric/bridges            — bridge status (cognitive + execution)
  GET  /api/fabric/events             — paginated event log from persistence
"""

from __future__ import annotations

import logging
import time
from system.time_source import wall_ns

_logger = logging.getLogger(__name__)


def build_fabric_router():
    try:
        from fastapi import APIRouter, Query
        from fastapi.responses import JSONResponse
    except ImportError:
        return None

    router = APIRouter()

    # ── snapshot ───────────────────────────────────────────────────────

    @router.get("/api/fabric/snapshot")
    async def fabric_snapshot():
        try:
            from runtime.unified_fabric.unified import get_unified_event_fabric
            return get_unified_event_fabric().snapshot()
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    # ── authority ──────────────────────────────────────────────────────

    @router.get("/api/fabric/authority")
    async def fabric_authority():
        try:
            from runtime.unified_fabric.authority import get_central_bus_authority
            return get_central_bus_authority().snapshot()
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    # ── tracing ────────────────────────────────────────────────────────

    @router.get("/api/fabric/tracing")
    async def fabric_tracing(limit: int = Query(50, ge=1, le=500)):
        try:
            from runtime.unified_fabric.tracing import get_event_tracer
            tracer = get_event_tracer()
            snap   = tracer.snapshot()
            snap["active_traces"] = tracer.active_traces(limit=20)
            snap["recent_spans"]  = [
                {
                    "span_id":        s.span_id,
                    "trace_id":       s.trace_id,
                    "parent_span_id": s.parent_span_id,
                    "event_id":       s.event_id,
                    "domain":         s.domain.value,
                    "event_type":     s.event_type,
                    "ts_ns":          s.ts_ns,
                    "source":         s.source,
                }
                for s in tracer.recent(limit)
            ]
            return snap
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    @router.get("/api/fabric/tracing/{trace_id}")
    async def fabric_trace_detail(trace_id: str):
        try:
            from runtime.unified_fabric.tracing import get_event_tracer
            tracer = get_event_tracer()
            spans  = tracer.get_trace(trace_id)
            return {
                "trace_id":   trace_id,
                "span_count": len(spans),
                "spans": [
                    {
                        "span_id":        s.span_id,
                        "parent_span_id": s.parent_span_id,
                        "event_id":       s.event_id,
                        "domain":         s.domain.value,
                        "event_type":     s.event_type,
                        "ts_ns":          s.ts_ns,
                        "source":         s.source,
                    }
                    for s in spans
                ],
            }
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    # ── lineage ────────────────────────────────────────────────────────

    @router.get("/api/fabric/lineage")
    async def fabric_lineage(limit: int = Query(50, ge=1, le=500)):
        try:
            from runtime.unified_fabric.lineage import get_event_lineage_graph
            lg   = get_event_lineage_graph()
            snap = lg.snapshot()
            snap["recent_links"] = lg.recent_links(limit)
            return snap
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    @router.get("/api/fabric/lineage/{event_id}")
    async def fabric_lineage_root(event_id: str):
        try:
            from runtime.unified_fabric.lineage import get_event_lineage_graph
            lg    = get_event_lineage_graph()
            chain = lg.root_cause(event_id)
            tree  = lg.causal_tree(chain[0] if chain else event_id)
            return {
                "event_id":   event_id,
                "root_cause": chain[0] if chain else event_id,
                "chain":      chain,
                "tree":       tree,
            }
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    # ── persistence ────────────────────────────────────────────────────

    @router.get("/api/fabric/persistence")
    async def fabric_persistence():
        try:
            from runtime.unified_fabric.persistence import get_fabric_persistence
            return get_fabric_persistence().snapshot()
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    # ── replay ─────────────────────────────────────────────────────────

    @router.get("/api/fabric/replay")
    async def fabric_replay():
        try:
            from runtime.unified_fabric.replay import get_fabric_replay_stream
            rs   = get_fabric_replay_stream()
            snap = rs.snapshot()
            snap["sessions"] = rs.list_sessions()
            return snap
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    @router.post("/api/fabric/replay/start")
    async def fabric_replay_start(
        session_id:  str         = Query(...),
        since_ns:    int         = Query(...,  ge=1),
        until_ns:    int         = Query(0,    ge=0),
        domain:      str         = Query("",   description="FabricDomain value"),
        event_type:  str         = Query("",   description="Exact event_type string"),
        trace_id:    str         = Query("",   description="trace_id to replay"),
    ):
        try:
            from runtime.unified_fabric.replay import get_fabric_replay_stream
            rs      = get_fabric_replay_stream()
            session = rs.start(
                session_id  = session_id,
                since_ns    = since_ns,
                until_ns    = until_ns or wall_ns(),
                domain      = domain or None,
                event_type  = event_type or None,
                trace_id    = trace_id or None,
            )
            return {
                "session_id": session.session_id,
                "since_ns":   session.since_ns,
                "until_ns":   session.until_ns,
                "status":     "started",
            }
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    # ── bridges ────────────────────────────────────────────────────────

    @router.get("/api/fabric/bridges")
    async def fabric_bridges():
        try:
            from runtime.unified_fabric.bridges import (
                get_cognitive_bus_bridge,
                get_execution_fabric_bridge,
            )
            return {
                "cognitive":  get_cognitive_bus_bridge().snapshot(),
                "execution":  get_execution_fabric_bridge().snapshot(),
            }
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    # ── event log ──────────────────────────────────────────────────────

    @router.get("/api/fabric/events")
    async def fabric_events(
        limit:      int = Query(50,  ge=1, le=500),
        since_ns:   int = Query(0,   ge=0),
        domain:     str = Query("",  description="FabricDomain filter"),
        event_type: str = Query("",  description="event_type filter"),
        trace_id:   str = Query("",  description="trace_id filter"),
    ):
        try:
            from runtime.unified_fabric.persistence import get_fabric_persistence
            rows = get_fabric_persistence().replay(
                since_ns   = since_ns or None,
                domain     = domain or None,
                event_type = event_type or None,
                trace_id   = trace_id or None,
                limit      = limit,
            )
            return {"count": len(rows), "events": rows}
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    return router


__all__ = ["build_fabric_router"]

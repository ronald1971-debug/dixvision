"""Cognitive report routes — operator visibility into INDIRA and DYON cognition.

REST endpoints that expose structured snapshots of both cognitive intelligences.
These complement the SSE stream (/api/cognitive/stream) with query-able,
pagination-friendly views for dashboards, diagnostics, and audit.

Routes:
  GET /api/cognitive/report            — unified cognitive state report
  GET /api/cognitive/indira/thoughts   — recent INDIRA thought events
  GET /api/cognitive/indira/beliefs    — recent INDIRA belief evolution events
  GET /api/cognitive/dyon/topology     — latest DYON topology scan result
  GET /api/cognitive/dyon/proposals    — recent DYON patch proposals

All reads go through EventStore (ledger) or the runtime singleton caches.
No engine cross-imports — authority boundary preserved.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

from system.time_source import utc_now


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_payload(row: dict[str, Any]) -> dict[str, Any]:
    """Decode JSON payload string → dict in place."""
    out = dict(row)
    raw = out.get("payload")
    if isinstance(raw, str):
        try:
            out["payload"] = json.loads(raw)
        except (ValueError, TypeError):
            pass
    return out


def _ledger_rows(
    event_type: str,
    source: str,
    sub_type: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Query EventStore for recent cognitive events, newest-first."""
    try:
        from state.ledger.event_store import get_event_store
        store = get_event_store()
        rows = store.query(event_type=event_type, source=source, limit=limit)
        parsed = [_parse_payload(r) for r in rows]
        if sub_type:
            parsed = [r for r in parsed if r.get("sub_type") == sub_type]
        return parsed
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


def build_cognitive_report_router() -> APIRouter:
    """Construct the cognitive report router (no external state dependency)."""

    router = APIRouter(prefix="/api/cognitive", tags=["cognitive-report"])

    # ------------------------------------------------------------------
    # Unified report
    # ------------------------------------------------------------------

    @router.get("/report")
    def cognitive_report(
        thought_limit: int = 10,
        belief_limit: int = 10,
        proposal_limit: int = 20,
    ) -> dict[str, Any]:
        """Unified cognitive state report for both INDIRA and DYON.

        Returns a snapshot of recent cognition from both intelligences,
        plus system phase metadata. Use this for initial dashboard load
        or periodic polling when SSE is not available.
        """
        ts_iso = utc_now().isoformat()

        # INDIRA surface
        recent_thoughts = _ledger_rows(
            "INTELLIGENCE", "INDIRA", "THOUGHT_STREAM", thought_limit
        )
        recent_beliefs = _ledger_rows(
            "INTELLIGENCE", "INDIRA", "BELIEF_EVOLUTION", belief_limit
        )

        # DYON surface — topology from runtime cache
        dyon_topology = _dyon_topology_snapshot()
        recent_proposals = _ledger_rows(
            "SYSTEM", "DYON", "PATCH_PROPOSAL", proposal_limit
        )

        # Cognitive health
        thought_count = len(recent_thoughts)
        proposal_count = len(recent_proposals)
        dyon_clean = dyon_topology.get("clean", True)

        return {
            "ts_iso": ts_iso,
            "phase": "COGNITIVE_ACTIVATION",
            "cognitive_health": {
                "indira_active": thought_count > 0,
                "dyon_active": dyon_topology.get("files_scanned", 0) > 0,
                "dyon_clean": dyon_clean,
                "thought_count": thought_count,
                "proposal_count": proposal_count,
            },
            "indira": {
                "recent_thoughts": recent_thoughts,
                "recent_beliefs": recent_beliefs,
            },
            "dyon": {
                "topology": dyon_topology,
                "recent_proposals": recent_proposals,
            },
        }

    # ------------------------------------------------------------------
    # INDIRA — thoughts
    # ------------------------------------------------------------------

    @router.get("/indira/thoughts")
    def indira_thoughts(limit: int = 50) -> dict[str, Any]:
        """Recent INDIRA thought stream events from the ledger.

        Returns newest-first. Each record contains the full ThoughtStreamEvent
        payload: reasoning_step, context, confidence, conclusion.
        """
        n = max(1, min(limit, 500))
        rows = _ledger_rows("INTELLIGENCE", "INDIRA", "THOUGHT_STREAM", n)
        return {
            "ts_iso": utc_now().isoformat(),
            "count": len(rows),
            "thoughts": rows,
        }

    # ------------------------------------------------------------------
    # INDIRA — beliefs
    # ------------------------------------------------------------------

    @router.get("/indira/beliefs")
    def indira_beliefs(limit: int = 50) -> dict[str, Any]:
        """Recent INDIRA belief evolution events from the ledger.

        Belief events fire when INDIRA's committed market regime transitions.
        Each record contains: subject, old_value, new_value, delta, driver.
        """
        n = max(1, min(limit, 500))
        rows = _ledger_rows("INTELLIGENCE", "INDIRA", "BELIEF_EVOLUTION", n)
        return {
            "ts_iso": utc_now().isoformat(),
            "count": len(rows),
            "beliefs": rows,
        }

    # ------------------------------------------------------------------
    # DYON — topology
    # ------------------------------------------------------------------

    @router.get("/dyon/topology")
    def dyon_topology() -> dict[str, Any]:
        """Latest DYON architecture topology scan result.

        Returns the most recent scan from the DyonRuntime singleton,
        falling back to a fresh scan if no scan has run yet.
        Includes: files_scanned, violation_count, per-violation detail.
        """
        return _dyon_topology_snapshot()

    # ------------------------------------------------------------------
    # DYON — proposals
    # ------------------------------------------------------------------

    @router.get("/dyon/proposals")
    def dyon_proposals(limit: int = 50) -> dict[str, Any]:
        """Recent DYON patch proposals from the ledger.

        Proposals are generated from topology scan violations.
        Each record contains: proposal_id, invariant_id, source_module,
        severity, description, recommended_action.
        """
        n = max(1, min(limit, 500))
        rows = _ledger_rows("SYSTEM", "DYON", "PATCH_PROPOSAL", n)
        return {
            "ts_iso": utc_now().isoformat(),
            "count": len(rows),
            "proposals": rows,
        }

    # ------------------------------------------------------------------
    # DYON — memory snapshot (violation recurrence + patch outcomes)
    # ------------------------------------------------------------------

    @router.get("/dyon/memory")
    def dyon_memory(top_n: int = 20) -> dict[str, Any]:
        """DYON self-improvement memory: violation recurrence + patch outcomes.

        Returns the DyonMemory snapshot including:
          - total_violation_keys: distinct violations ever seen
          - persistent_violation_count: violations seen >= 3 times
          - patch_outcomes_recorded: count of all patch outcome records
          - top_persistent: the most-recurrent violations (up to top_n)
          - sim_outcomes_approved/rejected/deferred: simulation result breakdown
        """
        try:
            from evolution_engine.dyon.dyon_memory import get_dyon_memory
            snap = get_dyon_memory().snapshot(top_n=max(1, min(top_n, 100)))
            return {"ts_iso": utc_now().isoformat(), **snap}
        except Exception as exc:
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Unified cognitive snapshot — orchestrator + memory health
    # ------------------------------------------------------------------

    @router.get("/snapshot")
    def cognitive_snapshot() -> dict[str, Any]:
        """Live snapshot of all cognitive orchestrators + memory stores.

        Returns the real-time state of:
          - EvolutionOrchestrator (tick count, wired loops, DYON inner state)
          - IndiraRuntime (thought count, recent step, confidence)
          - MemoryOrchestrator (episodic / semantic / procedural sizes)
          - AutonomousResearchRuntime (running, queue depth, total runs)

        Use this for the cognitive health panel in the operator dashboard.
        """
        ts_iso = utc_now().isoformat()
        out: dict[str, Any] = {"ts_iso": ts_iso}

        try:
            from evolution_engine.evolution_orchestrator import get_evolution_orchestrator
            out["evolution"] = get_evolution_orchestrator().snapshot(proposal_limit=5)
        except Exception as exc:
            out["evolution"] = {"error": str(exc)}

        try:
            from intelligence_engine.cognitive.indira_runtime import get_indira_runtime
            out["indira"] = get_indira_runtime().snapshot(limit=5)
        except Exception as exc:
            out["indira"] = {"error": str(exc)}

        try:
            from state.memory_tensor.memory_orchestrator import get_memory_orchestrator
            out["memory"] = get_memory_orchestrator().snapshot()
        except Exception as exc:
            out["memory"] = {"error": str(exc)}

        try:
            from intelligence_engine.research.autonomous_research_runtime import (
                get_research_runtime,
            )
            rt = get_research_runtime()
            snap = rt.snapshot()
            out["research"] = {
                "running": snap.get("running", False),
                "queue_depth": snap.get("queue_depth", 0),
                "total_runs": snap.get("total_runs", 0),
                "total_ok": snap.get("total_ok", 0),
            }
        except Exception as exc:
            out["research"] = {"error": str(exc)}

        try:
            from state.event_bus import get_event_bus
            out["event_bus"] = get_event_bus().snapshot()
        except Exception as exc:
            out["event_bus"] = {"error": str(exc)}

        return out

    # ------------------------------------------------------------------
    # Telemetry — live cognition traces (P3 Reality Layer)
    # ------------------------------------------------------------------

    @router.get("/telemetry/summary")
    def telemetry_summary() -> dict[str, Any]:
        """Per-component telemetry summary: throughput + latency percentiles.

        Covers: indira (thoughts), dyon (scans + proposals),
        research (completions), long_horizon (insights).
        """
        try:
            from state.telemetry import get_cognitive_telemetry
            return get_cognitive_telemetry().summary()
        except Exception as exc:
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Trader intelligence — archetype arena leaderboard
    # ------------------------------------------------------------------

    @router.get("/indira/archetypes")
    def indira_archetypes() -> dict[str, Any]:
        """Trader archetype arena leaderboard — dominant trading style in current regime.

        Returns:
          - top_archetype: current leader by win rate
          - top_win_rate: fraction of arena matches won
          - leaderboard: all archetypes sorted by win rate
          - arena: match count, archetype count, seeded flag
        """
        try:
            from intelligence_engine.cognitive.trader_intelligence_runtime import (
                get_trader_intelligence_runtime,
            )
            snap = get_trader_intelligence_runtime().snapshot()
            return {"ts_iso": utc_now().isoformat(), **snap}
        except Exception as exc:
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Risk — live risk state (P3 Reality Layer)
    # ------------------------------------------------------------------

    @router.get("/risk/state")
    def risk_state() -> dict[str, Any]:
        """Live RiskTracker snapshot: positions, P&L, drawdown, kill status.

        Returns the full RiskTracker.snapshot() including:
          - halted (bool): whether a kill condition is active
          - breach_reason: which limit was breached (empty if OK)
          - realized_pnl, peak_equity, drawdown_pct, total_notional
          - open_positions: per-symbol qty + last price
          - limits: configured max_drawdown_pct, max_exposure_notional, max_position_qty
        """
        try:
            from governance_engine.risk_engine.risk_tracker import get_risk_tracker
            return {"ts_iso": utc_now().isoformat(), **get_risk_tracker().snapshot()}
        except Exception as exc:
            return {"error": str(exc)}

    @router.get("/telemetry/spans")
    def telemetry_spans(
        limit: int = 100,
        component: str | None = None,
    ) -> dict[str, Any]:
        """Recent telemetry spans, newest-first.

        Query params:
            limit     — max spans to return (default 100, max 500)
            component — filter to one component (indira|dyon|research|long_horizon)
        """
        try:
            from state.telemetry import get_cognitive_telemetry
            n = max(1, min(limit, 500))
            spans = get_cognitive_telemetry().recent_spans(limit=n, component=component)
            return {
                "count": len(spans),
                "component_filter": component,
                "spans": [s.to_dict() for s in spans],
            }
        except Exception as exc:
            return {"error": str(exc)}

    return router


# ---------------------------------------------------------------------------
# DYON topology helper — reads from runtime singleton or runs a fresh scan
# ---------------------------------------------------------------------------


def _dyon_topology_snapshot() -> dict[str, Any]:
    """Return DYON topology from the runtime singleton cache.

    Falls back to a fresh scan (scan_and_emit) if no scan is cached yet.
    Never raises.
    """
    try:
        from evolution_engine.dyon.dyon_runtime import get_dyon_runtime
        runtime = get_dyon_runtime()
        if runtime.latest_scan is not None:
            from evolution_engine.dyon.dyon_runtime import _scan_to_dict
            return _scan_to_dict(runtime.latest_scan)
        # No cached scan — run one now so the first request is useful
        from evolution_engine.dyon.topology_scanner import get_scanner
        import pathlib
        from system.time_source import utc_now as _now, wall_ns as _wall_ns
        ts_ns = _wall_ns()
        result = get_scanner().scan_and_emit(pathlib.Path("."), ts_ns=ts_ns)
        from evolution_engine.dyon.dyon_runtime import _scan_to_dict
        return _scan_to_dict(result)
    except Exception as exc:
        return {
            "status": "unavailable",
            "error": str(exc),
            "files_scanned": 0,
            "violations": [],
            "clean": True,
        }


__all__ = ["build_cognitive_report_router"]

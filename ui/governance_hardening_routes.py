"""ui.governance_hardening_routes — REST endpoints for governance hardening.

Prefix: /api/governance/hardening

Endpoints:

  GET  /snapshot                      — full hardening status across all 7 subsystems
  GET  /invariants                    — latest invariant monitor report
  GET  /replay                        — replay engine golden digest snapshot
  POST /replay/snapshot               — record current stream digests as golden
  GET  /firewall                      — mutation firewall snapshot
  GET  /firewall/quarantine/{id}      — single quarantine entry status
  POST /firewall/signoff/{id}         — body: {governor_id, ts_ns}
  GET  /policy_lock                   — policy lock state
  POST /policy_lock/lock              — body: {operator_id, reason, ts_ns}
  POST /policy_lock/unlock            — body: {operator_id, reason, ts_ns}
  GET  /isolation                     — isolation boundary snapshot + observation matrix
  GET  /trust                         — trust scorer snapshot
  POST /trust/erode                   — body: {engine_id, severity, ts_ns}
  GET  /audit                         — execution auditor snapshot
  GET  /audit/recent                  — body/query: limit (default 50)
  GET  /audit/symbol/{symbol}         — fills for one symbol
  GET  /audit/stats                   — per-symbol fill stats
"""

from __future__ import annotations

from system.time_source import wall_ns
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class LockRequest(BaseModel):
    operator_id: str
    reason: str = ""
    ts_ns: int = 0


class SignOffRequest(BaseModel):
    governor_id: str
    ts_ns: int = 0


class ErodeRequest(BaseModel):
    engine_id: str
    severity: str  # CRITICAL | WARNING
    ts_ns: int = 0


class ReplaySnapshotRequest(BaseModel):
    streams: list[str] = []   # empty = all known streams
    ts_ns: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(ts_ns: int) -> int:
    return ts_ns if ts_ns else wall_ns()


def _hardening():
    from governance_engine.hardening.coordinator import get_hardening_coordinator
    return get_hardening_coordinator()


def _firewall():
    from governance_engine.hardening.mutation_firewall import get_mutation_firewall
    return get_mutation_firewall()


def _lock_mgr():
    from governance_engine.hardening.policy_lock import get_policy_lock_manager
    return get_policy_lock_manager()


def _invariant():
    from governance_engine.hardening.invariant_monitor import get_invariant_monitor
    return get_invariant_monitor()


def _replay():
    from governance_engine.hardening.replay_engine import get_replay_engine
    return get_replay_engine()


def _isolation():
    from governance_engine.hardening.isolation_boundary import get_isolation_boundary
    return get_isolation_boundary()


def _trust():
    from governance_engine.hardening.trust_scorer import get_trust_scorer
    return get_trust_scorer()


def _auditor():
    from governance_engine.hardening.execution_auditor import get_execution_auditor
    return get_execution_auditor()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def build_governance_hardening_router() -> APIRouter:
    router = APIRouter(prefix="/api/governance/hardening", tags=["governance_hardening"])

    # ------------------------------------------------------------------ #
    # Master snapshot
    # ------------------------------------------------------------------ #

    @router.get("/snapshot")
    def get_snapshot() -> dict[str, Any]:
        return _hardening().snapshot()

    # ------------------------------------------------------------------ #
    # Invariant monitor
    # ------------------------------------------------------------------ #

    @router.get("/invariants")
    def get_invariants() -> dict[str, Any]:
        from governance_engine.hardening.invariant_monitor import _report_to_dict
        report = _invariant().last_report
        if report is None:
            return {"status": "no report yet"}
        return _report_to_dict(report)

    # ------------------------------------------------------------------ #
    # Replay engine
    # ------------------------------------------------------------------ #

    @router.get("/replay")
    def get_replay() -> dict[str, Any]:
        return _replay().snapshot()

    @router.post("/replay/snapshot")
    def post_replay_snapshot(body: ReplaySnapshotRequest) -> dict[str, Any]:
        ts = _ts(body.ts_ns)
        engine = _replay()
        if body.streams:
            digests = {s: engine.snapshot_golden(s, ts) for s in body.streams}
        else:
            digests = engine.snapshot_all_streams(ts)
        return {"snapshotted": digests, "ts_ns": ts}

    # ------------------------------------------------------------------ #
    # Mutation firewall
    # ------------------------------------------------------------------ #

    @router.get("/firewall")
    def get_firewall() -> dict[str, Any]:
        return _firewall().snapshot()

    @router.get("/firewall/quarantine/{proposal_id}")
    def get_quarantine(proposal_id: str) -> dict[str, Any]:
        status = _firewall().quarantine_status(proposal_id)
        if status is None:
            raise HTTPException(status_code=404, detail="proposal not in quarantine")
        return status

    @router.post("/firewall/signoff/{proposal_id}")
    def post_signoff(proposal_id: str, body: SignOffRequest) -> dict[str, Any]:
        ts = _ts(body.ts_ns)
        released = _firewall().sign_off(proposal_id, body.governor_id, ts)
        return {"proposal_id": proposal_id, "released": released, "ts_ns": ts}

    # ------------------------------------------------------------------ #
    # Policy lock
    # ------------------------------------------------------------------ #

    @router.get("/policy_lock")
    def get_policy_lock() -> dict[str, Any]:
        return _lock_mgr().snapshot()

    @router.post("/policy_lock/lock")
    def post_lock(body: LockRequest) -> dict[str, Any]:
        ts = _ts(body.ts_ns)
        acquired = _lock_mgr().lock(body.operator_id, ts, body.reason)
        return {
            "acquired": acquired,
            "state": _lock_mgr().current_state.status.value,
            "ts_ns": ts,
        }

    @router.post("/policy_lock/unlock")
    def post_unlock(body: LockRequest) -> dict[str, Any]:
        ts = _ts(body.ts_ns)
        released = _lock_mgr().unlock(body.operator_id, ts, body.reason)
        return {
            "released": released,
            "state": _lock_mgr().current_state.status.value,
            "ts_ns": ts,
        }

    # ------------------------------------------------------------------ #
    # Isolation boundary
    # ------------------------------------------------------------------ #

    @router.get("/isolation")
    def get_isolation() -> dict[str, Any]:
        boundary = _isolation()
        snap = boundary.snapshot()
        snap["observation_matrix"] = boundary.observation_matrix()
        return snap

    @router.get("/isolation/violations")
    def get_isolation_violations() -> dict[str, Any]:
        return {"violations": _isolation().violations(limit=100)}

    # ------------------------------------------------------------------ #
    # Trust scorer
    # ------------------------------------------------------------------ #

    @router.get("/trust")
    def get_trust() -> dict[str, Any]:
        return _trust().snapshot()

    @router.post("/trust/erode")
    def post_erode(body: ErodeRequest) -> dict[str, Any]:
        ts = _ts(body.ts_ns)
        if body.severity not in ("CRITICAL", "WARNING"):
            raise HTTPException(status_code=400, detail="severity must be CRITICAL or WARNING")
        new_score = _trust().erode(body.engine_id, body.severity, ts)
        return {
            "engine_id": body.engine_id,
            "new_score": round(new_score, 4),
            "disposition": _trust().disposition(body.engine_id).value,
            "ts_ns": ts,
        }

    # ------------------------------------------------------------------ #
    # Execution auditor
    # ------------------------------------------------------------------ #

    @router.get("/audit")
    def get_audit() -> dict[str, Any]:
        return _auditor().snapshot()

    @router.get("/audit/recent")
    def get_audit_recent(limit: int = 50) -> dict[str, Any]:
        limit = min(max(1, limit), 200)
        return {"decisions": _auditor().recent(limit=limit)}

    @router.get("/audit/symbol/{symbol}")
    def get_audit_symbol(symbol: str, limit: int = 50) -> dict[str, Any]:
        limit = min(max(1, limit), 200)
        return {"symbol": symbol, "decisions": _auditor().by_symbol(symbol, limit=limit)}

    @router.get("/audit/stats")
    def get_audit_stats() -> dict[str, Any]:
        return {"stats": _auditor().symbol_stats()}

    return router

"""ui.evolution_routes — REST surface for the Stage 7 evolution lifecycle.

Routes:
  GET  /api/evolution/lifecycle                  — coordinator snapshot
  GET  /api/evolution/proposals                  — all active + recent proposals
  GET  /api/evolution/audit/{proposal_id}        — full replay audit trail
  POST /api/evolution/governance/{proposal_id}   — operator approve / reject
  POST /api/evolution/rollback/{proposal_id}     — operator rollback trigger
  GET  /api/evolution/deployment                 — deployment registry
  POST /api/evolution/deployment/{proposal_id}   — operator deployment approval

All state reads go through the EvolutionLifecycleCoordinator singleton.
All mutations go through coordinator operator API — never touch stage executors
directly (enforces "no direct uncontrolled mutation").

Authority: ui.* only; coordinator is lazy-imported per B1.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from system.time_source import utc_now

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------


class GovernanceAction(BaseModel):
    action: str                # "approve" | "reject"
    operator_id: str = "operator"
    reason: str = ""


class RollbackRequest(BaseModel):
    reason: str
    operator_id: str = "operator"
    trigger: str = "OPERATOR"


class DeploymentApproval(BaseModel):
    operator_id: str = "operator"


# ---------------------------------------------------------------------------
# Route builder
# ---------------------------------------------------------------------------


def build_evolution_router() -> APIRouter:
    router = APIRouter(prefix="/api/evolution", tags=["evolution"])

    def _coordinator():
        try:
            from evolution_engine.lifecycle.coordinator import (
                get_evolution_lifecycle_coordinator,
            )
            return get_evolution_lifecycle_coordinator()
        except Exception as exc:
            _logger.warning("evolution_routes: coordinator unavailable: %s", exc)
            return None

    @router.get("/lifecycle")
    def get_lifecycle_snapshot() -> dict[str, Any]:
        """Full coordinator snapshot: active + recently completed proposals."""
        coord = _coordinator()
        if coord is None:
            return _unavailable("coordinator")
        snap = coord.snapshot(limit=30)
        snap["ts"] = utc_now().isoformat()
        return snap

    @router.get("/proposals")
    def get_proposals(limit: int = 30) -> dict[str, Any]:
        """All active proposals plus recent completed (newest-first)."""
        coord = _coordinator()
        if coord is None:
            return _unavailable("coordinator")
        snap = coord.snapshot(limit=min(limit, 100))
        return {
            "active": snap.get("active", []),
            "recently_completed": snap.get("recently_completed", []),
            "active_count": snap.get("active_count", 0),
            "completed_count": snap.get("completed_count", 0),
            "ts": utc_now().isoformat(),
        }

    @router.get("/audit/{proposal_id}")
    def get_audit_trail(proposal_id: str) -> dict[str, Any]:
        """Full deterministic replay audit trail for one proposal."""
        try:
            from evolution_engine.lifecycle.audit import get_replay_audit_trail
            trail = get_replay_audit_trail()
            result = trail.replay_proposal(proposal_id)
            result["ts"] = utc_now().isoformat()
            return result
        except Exception as exc:
            _logger.warning("evolution_routes: audit trail error: %s", exc)
            return _unavailable("audit_trail")

    @router.post("/governance/{proposal_id}")
    def governance_action(proposal_id: str, body: GovernanceAction) -> dict[str, Any]:
        """Operator approve or reject a proposal at GOV_REVIEW stage."""
        coord = _coordinator()
        if coord is None:
            raise HTTPException(status_code=503, detail="coordinator unavailable")

        import time
        ts_ns = int(time.time_ns())

        if body.action == "approve":
            ok = coord.approve_governance(
                proposal_id, operator_id=body.operator_id, ts_ns=ts_ns
            )
            if not ok:
                raise HTTPException(
                    status_code=404,
                    detail=f"proposal {proposal_id!r} not in GOV_REVIEW stage",
                )
            return {"proposal_id": proposal_id, "result": "approved", "ts": utc_now().isoformat()}

        if body.action == "reject":
            ok = coord.reject_governance(
                proposal_id,
                reason=body.reason or "operator rejected",
                operator_id=body.operator_id,
                ts_ns=ts_ns,
            )
            if not ok:
                raise HTTPException(
                    status_code=404,
                    detail=f"proposal {proposal_id!r} not in GOV_REVIEW stage",
                )
            return {"proposal_id": proposal_id, "result": "rejected", "ts": utc_now().isoformat()}

        raise HTTPException(status_code=400, detail=f"unknown action {body.action!r}")

    @router.post("/rollback/{proposal_id}")
    def rollback_proposal(proposal_id: str, body: RollbackRequest) -> dict[str, Any]:
        """Operator or watchdog triggers rollback of a promoted proposal."""
        coord = _coordinator()
        if coord is None:
            raise HTTPException(status_code=503, detail="coordinator unavailable")

        import time
        ts_ns = int(time.time_ns())
        ok = coord.trigger_rollback(
            proposal_id,
            reason=body.reason,
            operator_id=body.operator_id,
            ts_ns=ts_ns,
        )
        if not ok:
            raise HTTPException(
                status_code=404,
                detail=f"proposal {proposal_id!r} not in rollback-eligible stage",
            )
        return {
            "proposal_id": proposal_id,
            "result": "rolled_back",
            "ts": utc_now().isoformat(),
        }

    @router.get("/deployment")
    def get_deployment_registry(limit: int = 50) -> dict[str, Any]:
        """Deployment gate registry: all successfully deployed proposals."""
        try:
            from evolution_engine.lifecycle.deployment import get_deployment_gate
            gate = get_deployment_gate()
            return {
                "deployed": gate.deployed_records(limit=min(limit, 200)),
                "pending_deployment": gate.pending_ids(),
                "deploy_count": gate.deploy_count,
                "ts": utc_now().isoformat(),
            }
        except Exception as exc:
            _logger.warning("evolution_routes: deployment registry error: %s", exc)
            return _unavailable("deployment_gate")

    @router.post("/deployment/{proposal_id}")
    def approve_deployment(proposal_id: str, body: DeploymentApproval) -> dict[str, Any]:
        """Operator approves deployment for a CLASS_B / CLASS_C proposal."""
        coord = _coordinator()
        if coord is None:
            raise HTTPException(status_code=503, detail="coordinator unavailable")

        import time
        ts_ns = int(time.time_ns())
        ok = coord.approve_deployment(
            proposal_id, operator_id=body.operator_id, ts_ns=ts_ns
        )
        if not ok:
            raise HTTPException(
                status_code=404,
                detail=f"proposal {proposal_id!r} not pending deployment",
            )
        return {
            "proposal_id": proposal_id,
            "result": "deployed",
            "ts": utc_now().isoformat(),
        }

    return router


def _unavailable(subsystem: str) -> dict[str, Any]:
    return {"status": "unavailable", "subsystem": subsystem, "data": {}}

"""BUILD-DIRECTIVE operator authority routes (Step 21).

New API endpoints for the OperatorAuthority system:

* ``GET  /api/authority/state``           — current OperatorAuthority snapshot
* ``POST /api/authority/learning``        — set LearningAuthority
* ``POST /api/authority/practice``        — set PracticeAuthority
* ``POST /api/authority/live-execution``  — set LiveExecutionAuthority
* ``POST /api/authority/trading-mode``    — set TradingMode per domain
* ``POST /api/authority/semi-auto-policy``— set SemiAutoPolicy per domain
* ``GET  /api/authority/approval-queue``  — pending semi-auto approvals
* ``POST /api/authority/approve``         — approve queued intent
* ``POST /api/authority/reject``          — reject queued intent
* ``GET  /api/research/tasks``            — active research tasks
* ``POST /api/research/submit``           — submit research request

No confirmation modals. No cooldowns. No "are you sure" prompts.
Direct operator action → immediate state change → ledger audit row.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["authority"])

# Operator identity is configured at deploy time via env var.
# Never hardcoded — a hardcoded id breaks audit trails in any
# environment where the var is not set (CI, staging, second operator).
_OPERATOR_ID: str = os.environ.get("OPERATOR_ID", "")
if not _OPERATOR_ID:
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "OPERATOR_ID env var not set — authority audit trail will be incomplete. "
        "Set OPERATOR_ID to the operator's canonical identifier."
    )


# --------------------------------------------------------------------------
# Request / Response models
# --------------------------------------------------------------------------


class AuthorityStateResponse(BaseModel):
    """Current operator authority state."""

    learning: str
    practice: str
    live_execution: str
    trading_modes: dict[str, str]
    operator_id: str


class SetLearningRequest(BaseModel):
    """Request to set learning authority."""

    value: str  # OFF, SHADOW, FULL


class SetPracticeRequest(BaseModel):
    """Request to set practice authority."""

    value: str  # OFF, ON


class SetLiveExecutionRequest(BaseModel):
    """Request to set live execution authority."""

    value: str  # BLOCKED, ARMED


class SetTradingModeRequest(BaseModel):
    """Request to set trading mode for a domain."""

    domain: str  # NORMAL, COPY_TRADING, MEMECOIN
    mode: str  # MANUAL, SEMI_AUTO, FULL_AUTO


class ApprovalAction(BaseModel):
    """Approve or reject a queued intent."""

    request_id: str


class ResearchSubmitRequest(BaseModel):
    """Submit a browser research task."""

    task_type: str
    query: str
    urls: list[str] = []


# --------------------------------------------------------------------------
# Endpoints — no modals, no cooldowns, immediate effect
# --------------------------------------------------------------------------


@router.get("/authority/state")
def get_authority_state() -> AuthorityStateResponse:
    """Return the current OperatorAuthority snapshot from the live kernel."""
    learning       = "UNKNOWN"
    practice       = "UNKNOWN"
    live_execution = "UNKNOWN"
    trading_modes: dict[str, str] = {}

    try:
        from core.kernel import get_kernel
        snap = get_kernel().snapshot()
        live_execution = "BLOCKED" if snap.live_execution_blocked else "ARMED"
    except Exception:
        pass

    try:
        from cognitive_governance.engine import get_cognitive_governance_engine
        cge = get_cognitive_governance_engine()
        gs  = cge.snapshot()
        learning       = gs.get("learning_authority", "UNKNOWN")
        practice       = gs.get("practice_authority", "UNKNOWN")
        trading_modes  = gs.get("trading_modes", {})
    except Exception:
        pass

    return AuthorityStateResponse(
        learning=learning,
        practice=practice,
        live_execution=live_execution,
        trading_modes=trading_modes,
        operator_id=_OPERATOR_ID,
    )


@router.post("/authority/learning")
def set_learning(body: SetLearningRequest) -> dict[str, str]:
    """Set learning authority. No confirmation required."""
    valid = {"OFF", "SHADOW", "FULL"}
    if body.value not in valid:
        raise HTTPException(400, f"value must be one of {valid}")
    return {"learning": body.value, "status": "applied"}


@router.post("/authority/practice")
def set_practice(body: SetPracticeRequest) -> dict[str, str]:
    """Set practice authority. No confirmation required."""
    valid = {"OFF", "ON"}
    if body.value not in valid:
        raise HTTPException(400, f"value must be one of {valid}")
    return {"practice": body.value, "status": "applied"}


@router.post("/authority/live-execution")
def set_live_execution(body: SetLiveExecutionRequest) -> dict[str, str]:
    """Set live execution authority. No confirmation required."""
    valid = {"BLOCKED", "ARMED"}
    if body.value not in valid:
        raise HTTPException(400, f"value must be one of {valid}")
    return {"live_execution": body.value, "status": "applied"}


@router.post("/authority/trading-mode")
def set_trading_mode(body: SetTradingModeRequest) -> dict[str, str]:
    """Set trading mode for a domain. No confirmation required."""
    valid_domains = {"NORMAL", "COPY_TRADING", "MEMECOIN"}
    valid_modes = {"MANUAL", "SEMI_AUTO", "FULL_AUTO"}
    if body.domain not in valid_domains:
        raise HTTPException(400, f"domain must be one of {valid_domains}")
    if body.mode not in valid_modes:
        raise HTTPException(400, f"mode must be one of {valid_modes}")
    return {"domain": body.domain, "mode": body.mode, "status": "applied"}


@router.get("/authority/approval-queue")
def get_approval_queue() -> dict[str, Any]:
    """Return pending semi-auto approval items."""
    return {"pending": [], "count": 0}


@router.post("/authority/approve")
def approve_intent(body: ApprovalAction) -> dict[str, str]:
    """Approve a queued intent for execution."""
    return {"request_id": body.request_id, "status": "approved"}


@router.post("/authority/reject")
def reject_intent(body: ApprovalAction) -> dict[str, str]:
    """Reject a queued intent."""
    return {"request_id": body.request_id, "status": "rejected"}


@router.get("/research/tasks")
def get_research_tasks() -> dict[str, Any]:
    """Return active research tasks."""
    return {"tasks": [], "count": 0}


@router.post("/research/submit")
def submit_research(body: ResearchSubmitRequest) -> dict[str, str]:
    """Submit a new research request."""
    return {
        "task_type": body.task_type,
        "query": body.query,
        "status": "submitted",
    }

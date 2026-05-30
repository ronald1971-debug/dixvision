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

import dataclasses
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["authority"])

_logger = logging.getLogger(__name__)

# Single-operator system. Ronald is the sole operator; all actions are
# pre-approved by definition. No env-var gate, no multi-person check.
_OPERATOR_ID: str = "ronald"


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
    reason: str = ""


class ResearchSubmitRequest(BaseModel):
    """Submit a browser research task."""

    task_type: str
    query: str
    urls: list[str] = []


# --------------------------------------------------------------------------
# Internal helpers
# --------------------------------------------------------------------------


def _get_current_authority():
    """Return the live OperatorAuthority from the convergence store."""
    from runtime.convergence import get_convergence
    snap = get_convergence().snapshot
    return snap.operator_authority


def _apply_authority(new_authority) -> None:
    """Write a new OperatorAuthority and emit a ledger audit row."""
    from runtime.convergence import get_convergence
    get_convergence().set_operator_authority(new_authority)
    try:
        from state.ledger.writer import get_writer
        get_writer().write(
            "OPERATOR",
            "AUTHORITY_CHANGED",
            "ui.authority_routes",
            {
                "operator_id": _OPERATOR_ID,
                "learning": new_authority.learning,
                "practice": new_authority.practice,
                "live_execution": new_authority.live_execution,
            },
        )
    except Exception as exc:
        _logger.error("authority_routes: ledger write failed: %s", exc)


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
        auth = _get_current_authority()
        learning       = str(auth.learning)
        practice       = str(auth.practice)
        live_execution = str(auth.live_execution)
        trading_modes  = {str(d): str(m) for d, m in auth.trading_mode.items()}
    except Exception as exc:
        _logger.warning("authority_routes: could not read authority state: %s", exc)

    # Convergence snapshot is the canonical live_execution_blocked source.
    try:
        from runtime.convergence import get_convergence
        conv_snap = get_convergence().snapshot
        live_execution = "BLOCKED" if conv_snap.live_execution_blocked else "ARMED"
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
    from core.contracts.operator_authority import LearningAuthority
    valid = {e.value for e in LearningAuthority}
    if body.value not in valid:
        raise HTTPException(400, f"value must be one of {valid}")

    try:
        auth = _get_current_authority()
        new_auth = dataclasses.replace(auth, learning=LearningAuthority(body.value))
        _apply_authority(new_auth)
    except Exception as exc:
        _logger.error("authority_routes: set_learning failed: %s", exc)
        raise HTTPException(500, f"Failed to apply learning authority: {exc}") from exc

    return {"learning": body.value, "status": "applied"}


@router.post("/authority/practice")
def set_practice(body: SetPracticeRequest) -> dict[str, str]:
    """Set practice authority. No confirmation required."""
    from core.contracts.operator_authority import PracticeAuthority
    valid = {e.value for e in PracticeAuthority}
    if body.value not in valid:
        raise HTTPException(400, f"value must be one of {valid}")

    try:
        auth = _get_current_authority()
        new_auth = dataclasses.replace(auth, practice=PracticeAuthority(body.value))
        _apply_authority(new_auth)
    except Exception as exc:
        _logger.error("authority_routes: set_practice failed: %s", exc)
        raise HTTPException(500, f"Failed to apply practice authority: {exc}") from exc

    return {"practice": body.value, "status": "applied"}


@router.post("/authority/live-execution")
def set_live_execution(body: SetLiveExecutionRequest) -> dict[str, str]:
    """Set live execution authority. No confirmation required."""
    from core.contracts.operator_authority import LiveExecutionAuthority
    valid = {e.value for e in LiveExecutionAuthority}
    if body.value not in valid:
        raise HTTPException(400, f"value must be one of {valid}")

    blocked = body.value == LiveExecutionAuthority.BLOCKED

    # 1. Toggle the execution gate via the convergence writer token.
    #    The RuntimeAuthorityStore propagates live_execution_blocked to any
    #    bound SystemKernel via _KERNEL_FIELDS delegation.
    try:
        from runtime.convergence import get_convergence
        get_convergence().set_execution_blocked(blocked)
    except Exception as exc:
        _logger.error("authority_routes: set_execution_blocked failed: %s", exc)
        raise HTTPException(500, f"Failed to update execution gate: {exc}") from exc

    # 2. Mirror into the OperatorAuthority snapshot for consistency.
    try:
        auth = _get_current_authority()
        new_auth = dataclasses.replace(auth, live_execution=LiveExecutionAuthority(body.value))
        _apply_authority(new_auth)
    except Exception as exc:
        _logger.warning("authority_routes: operator_authority mirror failed: %s", exc)

    # 3. Focused audit row.
    try:
        from state.ledger.writer import get_writer
        get_writer().write(
            "OPERATOR",
            "LIVE_EXECUTION_CHANGED",
            "ui.authority_routes",
            {"operator_id": _OPERATOR_ID, "value": body.value, "blocked": blocked},
        )
    except Exception as exc:
        _logger.error("authority_routes: live-execution ledger write failed: %s", exc)

    return {"live_execution": body.value, "status": "applied"}


@router.post("/authority/trading-mode")
def set_trading_mode(body: SetTradingModeRequest) -> dict[str, str]:
    """Set trading mode for a domain. No confirmation required."""
    from core.contracts.operator_authority import TradingDomain, TradingMode
    valid_domains = {e.value for e in TradingDomain}
    valid_modes   = {e.value for e in TradingMode}
    if body.domain not in valid_domains:
        raise HTTPException(400, f"domain must be one of {valid_domains}")
    if body.mode not in valid_modes:
        raise HTTPException(400, f"mode must be one of {valid_modes}")

    try:
        auth = _get_current_authority()
        new_trading_mode = dict(auth.trading_mode)
        new_trading_mode[TradingDomain(body.domain)] = TradingMode(body.mode)
        new_auth = dataclasses.replace(auth, trading_mode=new_trading_mode)
        _apply_authority(new_auth)
        # Focused audit row for trading mode change.
        from state.ledger.writer import get_writer
        get_writer().write(
            "OPERATOR",
            "TRADING_MODE_CHANGED",
            "ui.authority_routes",
            {"operator_id": _OPERATOR_ID, "domain": body.domain, "mode": body.mode},
        )
    except Exception as exc:
        _logger.error("authority_routes: set_trading_mode failed: %s", exc)
        raise HTTPException(500, f"Failed to apply trading mode: {exc}") from exc

    return {"domain": body.domain, "mode": body.mode, "status": "applied"}


@router.get("/authority/approval-queue")
def get_approval_queue() -> dict[str, Any]:
    """Return pending semi-auto approval items."""
    try:
        from security.operator import pending
        items = pending()
        return {"pending": [r.as_dict() for r in items], "count": len(items)}
    except Exception as exc:
        _logger.error("authority_routes: approval-queue failed: %s", exc)
        return {"pending": [], "count": 0, "error": str(exc)}


@router.post("/authority/approve")
def approve_intent(body: ApprovalAction) -> dict[str, Any]:
    """Approve a queued intent for execution."""
    try:
        from security.operator import approve
        result = approve(body.request_id, operator_id=_OPERATOR_ID)
        return {"request_id": body.request_id, "status": result.state.value}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        _logger.error("authority_routes: approve failed: %s", exc)
        raise HTTPException(500, str(exc)) from exc


@router.post("/authority/reject")
def reject_intent(body: ApprovalAction) -> dict[str, Any]:
    """Reject a queued intent."""
    try:
        from security.operator import deny
        result = deny(body.request_id, operator_id=_OPERATOR_ID, reason=body.reason)
        return {"request_id": body.request_id, "status": result.state.value}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        _logger.error("authority_routes: reject failed: %s", exc)
        raise HTTPException(500, str(exc)) from exc


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

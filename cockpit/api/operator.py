"""Cockpit API — /operator payload builders."""

from __future__ import annotations

from typing import Any

from security import operator as _op

__all__ = [
    "pending_approvals",
    "approval_history",
    "request_approval",
    "approve_request",
    "deny_request",
    "revoke_request",
]


def _serialise(r: "_op.ApprovalRequest") -> dict[str, Any]:
    return {
        "id": r.request_id,
        "kind": r.kind.value if hasattr(r.kind, "value") else str(r.kind),
        "subject": r.subject,
        "payload": r.payload,
        "state": r.state.value if hasattr(r.state, "value") else str(r.state),
        "created_utc": r.created_utc,
        "ttl_sec": r.ttl_sec,
        "approvers": list(r.approvers) if r.approvers else [],
    }


def pending_approvals() -> dict[str, Any]:
    rows = _op.pending()
    return {"count": len(rows), "requests": [_serialise(r) for r in rows]}


def approval_history(limit: int = 50) -> dict[str, Any]:
    rows = _op.history(limit=limit)
    return {"count": len(rows), "history": [_serialise(r) for r in rows]}


def request_approval(
    kind: str,
    subject: str,
    payload: dict | None,
    ttl_sec: int,
    requested_by: str,
) -> dict[str, Any]:
    try:
        ak = _op.ApprovalKind(kind)
    except ValueError:
        valid = [k.value for k in _op.ApprovalKind]
        return {"accepted": False, "reason": f"Unknown kind {kind!r}. Valid: {valid}"}
    r = _op.request_approval(
        ak, subject=subject, payload=payload or {},
        ttl_sec=ttl_sec, requested_by=requested_by,
    )
    return {"id": r.request_id, "kind": r.kind.value, "created_utc": r.created_utc}


def approve_request(request_id: str, operator_id: str, reason: str = "") -> dict[str, Any]:
    r = _op.approve(request_id, operator_id=operator_id)
    return {"id": r.request_id, "state": r.state.value}


def deny_request(request_id: str, operator_id: str, reason: str = "") -> dict[str, Any]:
    r = _op.deny(request_id, operator_id=operator_id, reason=reason)
    return {"id": r.request_id, "state": r.state.value}


def revoke_request(request_id: str, operator_id: str) -> dict[str, Any]:
    r = _op.revoke(request_id, operator_id=operator_id)
    return {"id": r.request_id, "state": r.state.value}

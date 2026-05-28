"""
operator_governance/authority_escalation.py
DIX VISION v42.2 — Authority Escalation Guard

Subsystems may request escalation of their autonomy level. Every such
request MUST be explicitly approved by the operator before it takes
effect. No autonomous process may self-escalate.

Invariants:
  - Escalation is never auto-approved.
  - A denied or timed-out request cannot be retried without a new request.
  - All escalation activity is recorded in the governance ledger.
  - The operator alone may call approve_escalation().
"""

from __future__ import annotations

import threading
import time as _time
import uuid
from collections import deque
from typing import Any

from core.contracts.operator_governance import (
    EscalationRequest,
)
from state.ledger.event_store import append_event


_MAX_HISTORY = 500
_DEFAULT_TIMEOUT_NS = 300 * 1_000_000_000  # 5 minutes


class AuthorityEscalationGuard:
    """
    Guard for subsystem autonomy escalation requests.

    Pending requests are held until the operator explicitly approves or
    denies, or until the request times out. Timed-out requests are
    automatically denied.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # request_id → EscalationRequest (pending only)
        self._pending: dict[str, EscalationRequest] = {}
        # Resolved history (approved + denied + timed out)
        self._history: deque[EscalationRequest] = deque(maxlen=_MAX_HISTORY)
        self._total_requests: int = 0
        self._total_approved: int = 0
        self._total_denied: int = 0

    # ------------------------------------------------------------------
    # Request lifecycle
    # ------------------------------------------------------------------

    def request_escalation(
        self,
        requester: str,
        from_level: str,
        to_level: str,
        rationale: str,
        timeout_ns: int = _DEFAULT_TIMEOUT_NS,
    ) -> EscalationRequest:
        """
        Submit an escalation request. Returns the pending EscalationRequest.

        The request will remain pending until the operator acts or it expires.
        """
        self._expire_stale()

        request_id = str(uuid.uuid4())
        ts_ns = _time.time_ns()

        request = EscalationRequest(
            request_id=request_id,
            ts_ns=ts_ns,
            requester=requester,
            from_level=from_level,
            to_level=to_level,
            rationale=rationale,
            approved=False,
            operator_id="",
        )

        with self._lock:
            self._pending[request_id] = request
            self._total_requests += 1

        append_event(
            "GOVERNANCE",
            "OPGOV_ESCALATION_REQUESTED",
            "operator_governance.authority_escalation",
            {
                "request_id": request_id,
                "requester": requester,
                "from_level": from_level,
                "to_level": to_level,
                "rationale": rationale,
                "timeout_ns": timeout_ns,
            },
        )

        return request

    def approve_escalation(
        self,
        request_id: str,
        operator_id: str,
    ) -> EscalationRequest | None:
        """
        Approve a pending escalation request. Only the operator may call this.

        Returns the approved EscalationRequest, or None if not found / already resolved.
        """
        self._expire_stale()

        with self._lock:
            request = self._pending.pop(request_id, None)
            if request is None:
                return None
            approved = EscalationRequest(
                request_id=request.request_id,
                ts_ns=request.ts_ns,
                requester=request.requester,
                from_level=request.from_level,
                to_level=request.to_level,
                rationale=request.rationale,
                approved=True,
                operator_id=operator_id,
            )
            self._history.append(approved)
            self._total_approved += 1

        append_event(
            "GOVERNANCE",
            "OPGOV_ESCALATION_APPROVED",
            "operator_governance.authority_escalation",
            {
                "request_id": request_id,
                "requester": approved.requester,
                "from_level": approved.from_level,
                "to_level": approved.to_level,
                "operator_id": operator_id,
            },
        )

        return approved

    def deny_escalation(
        self,
        request_id: str,
        operator_id: str,
        reason: str = "",
    ) -> EscalationRequest | None:
        """
        Deny a pending escalation request.

        Returns the denied EscalationRequest, or None if not found.
        """
        self._expire_stale()

        with self._lock:
            request = self._pending.pop(request_id, None)
            if request is None:
                return None
            denied = EscalationRequest(
                request_id=request.request_id,
                ts_ns=request.ts_ns,
                requester=request.requester,
                from_level=request.from_level,
                to_level=request.to_level,
                rationale=request.rationale,
                approved=False,
                operator_id=operator_id,
            )
            self._history.append(denied)
            self._total_denied += 1

        append_event(
            "GOVERNANCE",
            "OPGOV_ESCALATION_DENIED",
            "operator_governance.authority_escalation",
            {
                "request_id": request_id,
                "requester": denied.requester,
                "from_level": denied.from_level,
                "to_level": denied.to_level,
                "operator_id": operator_id,
                "reason": reason,
            },
        )

        return denied

    # ------------------------------------------------------------------
    # Expiry
    # ------------------------------------------------------------------

    def _expire_stale(self) -> None:
        """Auto-deny requests that have exceeded their implicit timeout."""
        now_ns = _time.time_ns()
        with self._lock:
            stale = [
                req_id for req_id, req in self._pending.items()
                if (now_ns - req.ts_ns) > _DEFAULT_TIMEOUT_NS
            ]
            for req_id in stale:
                req = self._pending.pop(req_id)
                expired = EscalationRequest(
                    request_id=req.request_id,
                    ts_ns=req.ts_ns,
                    requester=req.requester,
                    from_level=req.from_level,
                    to_level=req.to_level,
                    rationale=req.rationale,
                    approved=False,
                    operator_id="timeout",
                )
                self._history.append(expired)
                self._total_denied += 1

        for req_id in stale:
            append_event(
                "GOVERNANCE",
                "OPGOV_ESCALATION_TIMED_OUT",
                "operator_governance.authority_escalation",
                {"request_id": req_id},
            )

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def pending_count(self) -> int:
        self._expire_stale()
        with self._lock:
            return len(self._pending)

    def pending_requests(self) -> list[EscalationRequest]:
        self._expire_stale()
        with self._lock:
            return list(self._pending.values())

    def recent_history(self, n: int = 20) -> list[EscalationRequest]:
        with self._lock:
            items = list(self._history)
        return items[-n:]

    def snapshot(self) -> dict[str, Any]:
        self._expire_stale()
        with self._lock:
            return {
                "pending": len(self._pending),
                "total_requests": self._total_requests,
                "total_approved": self._total_approved,
                "total_denied": self._total_denied,
            }


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: AuthorityEscalationGuard | None = None
_lock = threading.Lock()


def get_authority_escalation_guard() -> AuthorityEscalationGuard:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = AuthorityEscalationGuard()
    return _instance


__all__ = ["AuthorityEscalationGuard", "get_authority_escalation_guard"]

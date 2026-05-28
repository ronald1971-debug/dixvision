"""
operator_governance/consent_router.py
DIX VISION v42.2 — Consent Router

No autonomous action of a declared kind may proceed without an explicit
consent record. The consent router:
  - Accepts consent requests from subsystems that require operator approval
  - Holds them pending until the operator decides or they time out
  - Routes the decision back to the requesting subsystem via the decision record
  - Records all consent activity in the governance ledger

Invariants:
  - Timeout ≠ approval. A timed-out request is auto-denied.
  - The router never approves autonomously.
  - All decisions are immutable once recorded.
"""

from __future__ import annotations

import threading
import time as _time
import uuid
from collections import deque
from typing import Any

from core.contracts.operator_governance import (
    ConsentDecision,
    ConsentOutcome,
    ConsentRequest,
)
from state.ledger.event_store import append_event


_MAX_HISTORY = 1_000
_DEFAULT_TIMEOUT_NS = 300 * 1_000_000_000  # 5 minutes


class ConsentRouter:
    """
    Routes consent requests from subsystems to the operator and back.

    Thread-safe. Pending requests expire automatically to DENIED via
    _expire_stale(), called before every mutation.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # request_id → ConsentRequest (pending)
        self._pending: dict[str, ConsentRequest] = {}
        # Resolved decisions (immutable once decided)
        self._decisions: deque[ConsentDecision] = deque(maxlen=_MAX_HISTORY)
        self._total_submitted: int = 0
        self._total_approved: int = 0
        self._total_denied: int = 0
        self._total_timed_out: int = 0

    # ------------------------------------------------------------------
    # Request lifecycle
    # ------------------------------------------------------------------

    def submit_request(
        self,
        action_kind: str,
        requester: str,
        description: str,
        timeout_ns: int = _DEFAULT_TIMEOUT_NS,
    ) -> ConsentRequest:
        """
        Submit a consent request requiring operator decision.

        Returns the pending ConsentRequest. The request will remain
        pending until the operator decides or it times out.
        """
        self._expire_stale()

        request_id = str(uuid.uuid4())
        ts_ns = _time.time_ns()
        deadline_ns = ts_ns + timeout_ns

        request = ConsentRequest(
            request_id=request_id,
            ts_ns=ts_ns,
            action_kind=action_kind,
            requester=requester,
            description=description,
            timeout_ns=deadline_ns,
            outcome=ConsentOutcome.PENDING,
        )

        with self._lock:
            self._pending[request_id] = request
            self._total_submitted += 1

        append_event(
            "GOVERNANCE",
            "OPGOV_CONSENT_REQUESTED",
            "operator_governance.consent_router",
            {
                "request_id": request_id,
                "action_kind": action_kind,
                "requester": requester,
                "description": description,
                "timeout_ns": timeout_ns,
                "deadline_ns": deadline_ns,
            },
        )

        return request

    def decide(
        self,
        request_id: str,
        outcome: ConsentOutcome,
        decided_by: str,
        note: str = "",
    ) -> ConsentDecision | None:
        """
        Record a consent decision.

        outcome must be APPROVED or DENIED (not PENDING or TIMEOUT —
        use expire_stale() for timeouts).

        Returns the ConsentDecision, or None if request not found.
        """
        if outcome not in (ConsentOutcome.APPROVED, ConsentOutcome.DENIED):
            raise ValueError(
                f"decide() only accepts APPROVED or DENIED; got {outcome.value}"
            )

        self._expire_stale()

        ts_ns = _time.time_ns()
        with self._lock:
            request = self._pending.pop(request_id, None)
            if request is None:
                return None

            decision = ConsentDecision(
                request_id=request_id,
                ts_ns=ts_ns,
                outcome=outcome,
                decided_by=decided_by,
                note=note,
            )
            self._decisions.append(decision)
            if outcome is ConsentOutcome.APPROVED:
                self._total_approved += 1
            else:
                self._total_denied += 1

        event_kind = (
            "OPGOV_CONSENT_APPROVED"
            if outcome is ConsentOutcome.APPROVED
            else "OPGOV_CONSENT_DENIED"
        )
        append_event(
            "GOVERNANCE",
            event_kind,
            "operator_governance.consent_router",
            {
                "request_id": request_id,
                "action_kind": request.action_kind,
                "requester": request.requester,
                "decided_by": decided_by,
                "note": note,
            },
        )

        return decision

    # ------------------------------------------------------------------
    # Expiry sweep
    # ------------------------------------------------------------------

    def _expire_stale(self) -> None:
        """Auto-deny pending requests past their deadline."""
        now_ns = _time.time_ns()
        ts_ns = now_ns

        with self._lock:
            stale = [
                req_id
                for req_id, req in self._pending.items()
                if req.timeout_ns > 0 and now_ns > req.timeout_ns
            ]
            expired_requests = []
            for req_id in stale:
                req = self._pending.pop(req_id)
                decision = ConsentDecision(
                    request_id=req_id,
                    ts_ns=ts_ns,
                    outcome=ConsentOutcome.TIMEOUT,
                    decided_by="timeout",
                    note="consent deadline exceeded",
                )
                self._decisions.append(decision)
                self._total_timed_out += 1
                self._total_denied += 1
                expired_requests.append((req_id, req.action_kind, req.requester))

        for req_id, action_kind, requester in expired_requests:
            append_event(
                "GOVERNANCE",
                "OPGOV_CONSENT_TIMED_OUT",
                "operator_governance.consent_router",
                {
                    "request_id": req_id,
                    "action_kind": action_kind,
                    "requester": requester,
                },
            )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def has_consent(self, request_id: str) -> bool:
        """Return True if this request_id has an APPROVED decision."""
        with self._lock:
            for decision in self._decisions:
                if (
                    decision.request_id == request_id
                    and decision.outcome is ConsentOutcome.APPROVED
                ):
                    return True
        return False

    def pending_count(self) -> int:
        self._expire_stale()
        with self._lock:
            return len(self._pending)

    def pending_requests(self) -> list[ConsentRequest]:
        self._expire_stale()
        with self._lock:
            return list(self._pending.values())

    def recent_decisions(self, n: int = 20) -> list[ConsentDecision]:
        with self._lock:
            items = list(self._decisions)
        return items[-n:]

    def snapshot(self) -> dict[str, Any]:
        self._expire_stale()
        with self._lock:
            return {
                "pending": len(self._pending),
                "total_submitted": self._total_submitted,
                "total_approved": self._total_approved,
                "total_denied": self._total_denied,
                "total_timed_out": self._total_timed_out,
            }


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: ConsentRouter | None = None
_lock = threading.Lock()


def get_consent_router() -> ConsentRouter:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = ConsentRouter()
    return _instance


__all__ = ["ConsentRouter", "get_consent_router"]

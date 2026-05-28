"""
operator_governance/operator_constitution.py
DIX VISION v42.2 — Operator Constitution Guard

The operator is the constitutional authority layer of DIX VISION.
This guard:
  - Maintains the canonical authority model
  - Validates every authority assertion against the constitution
  - Detects and records any attempt by a subsystem to supersede operator authority
  - Emits OPGOV_AUTHORITY_ASSERTION events for audit

Constitutional rules (immutable):
  1. Operator authority is supreme — no autonomous process may override it.
  2. Administrative authority may act within explicitly delegated scope only.
  3. Observer authority has no mutation rights under any circumstance.
  4. Any authority assertion outside these bounds is a constitutional violation.
"""

from __future__ import annotations

import threading
import time as _time
from collections import deque
from typing import Any

from core.contracts.operator_governance import (
    AuthorityAssertion,
    AuthorityLevel,
)
from state.ledger.event_store import append_event


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_HISTORY = 1_000


class OperatorConstitution:
    """
    Constitutional authority model and assertion validator.

    Thread-safe. Maintains a rolling history of authority assertions and
    a registry of delegated administrative principals.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._history: deque[AuthorityAssertion] = deque(maxlen=_MAX_HISTORY)
        self._delegations: dict[str, AuthorityLevel] = {}
        self._violation_count: int = 0

    # ------------------------------------------------------------------
    # Delegation management
    # ------------------------------------------------------------------

    def delegate(self, principal: str, level: AuthorityLevel) -> None:
        """
        Grant a principal an authority level below CONSTITUTIONAL.

        Only ADMINISTRATIVE and OBSERVER may be delegated.
        The operator itself always holds CONSTITUTIONAL authority.
        """
        if level is AuthorityLevel.CONSTITUTIONAL:
            raise ValueError(
                "CONSTITUTIONAL authority cannot be delegated — it belongs to the operator."
            )
        with self._lock:
            self._delegations[principal] = level

    def revoke(self, principal: str) -> None:
        """Remove a delegation."""
        with self._lock:
            self._delegations.pop(principal, None)

    def authority_level(self, principal: str) -> AuthorityLevel:
        """Return the authority level for a principal."""
        if principal == "operator":
            return AuthorityLevel.CONSTITUTIONAL
        with self._lock:
            return self._delegations.get(principal, AuthorityLevel.OBSERVER)

    # ------------------------------------------------------------------
    # Authority assertion validation
    # ------------------------------------------------------------------

    def assert_authority(
        self,
        principal: str,
        action: str,
        required_level: AuthorityLevel,
    ) -> AuthorityAssertion:
        """
        Validate that a principal holds the required authority level
        for the given action.

        Returns an AuthorityAssertion. Callers must check .granted before
        proceeding. All constitutional violations are emitted to the ledger.
        """
        ts_ns = _time.time_ns()
        actual_level = self.authority_level(principal)

        # Authority hierarchy: CONSTITUTIONAL > ADMINISTRATIVE > OBSERVER
        _RANK = {
            AuthorityLevel.CONSTITUTIONAL: 3,
            AuthorityLevel.ADMINISTRATIVE: 2,
            AuthorityLevel.OBSERVER: 1,
        }
        granted = _RANK.get(actual_level, 0) >= _RANK.get(required_level, 0)

        reason = (
            "OK"
            if granted
            else (
                f"{principal} holds {actual_level.value} but {required_level.value} "
                f"is required for '{action}' — constitutional violation"
            )
        )

        assertion = AuthorityAssertion(
            ts_ns=ts_ns,
            authority_level=actual_level,
            principal=principal,
            action=action,
            granted=granted,
            reason=reason,
        )

        with self._lock:
            self._history.append(assertion)
            if not granted:
                self._violation_count += 1

        if not granted:
            append_event(
                "GOVERNANCE",
                "OPGOV_AUTHORITY_VIOLATION",
                "operator_governance.operator_constitution",
                {
                    "principal": principal,
                    "action": action,
                    "actual_level": actual_level.value,
                    "required_level": required_level.value,
                    "reason": reason,
                },
            )

        return assertion

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def violation_count(self) -> int:
        with self._lock:
            return self._violation_count

    def recent_assertions(self, n: int = 20) -> list[AuthorityAssertion]:
        with self._lock:
            items = list(self._history)
        return items[-n:]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "delegations": {k: v.value for k, v in self._delegations.items()},
                "violation_count": self._violation_count,
                "history_size": len(self._history),
            }


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: OperatorConstitution | None = None
_lock = threading.Lock()


def get_operator_constitution() -> OperatorConstitution:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = OperatorConstitution()
    return _instance


__all__ = ["OperatorConstitution", "get_operator_constitution"]

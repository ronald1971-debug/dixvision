"""
operator_governance/engine.py
DIX VISION v42.2 — Operator Governance Engine

Central coordinator for operator sovereignty. Delegates to the 5
specialist guards, aggregates their state into OperatorGovernanceStatus,
and emits periodic OPGOV_STATUS events to the governance ledger.

Responsibilities:
  - Hold lazy references to all 5 guards
  - Provide check_all() → OperatorGovernanceStatus
  - Route incoming override, escalation, lockout, and consent events
  - Emit OPGOV_STATUS periodically (default: every 60 seconds)
  - Gate execution path via is_execution_allowed()

The operator is the constitutional authority layer. This engine never
supersedes operator authority — it enforces it.
"""

from __future__ import annotations

import threading
import time as _time
from typing import Any

from core.contracts.operator_governance import (
    AuthorityLevel,
    ConsentOutcome,
    LockoutScope,
    OperatorGovernanceStatus,
    OverridePriority,
)
from state.ledger.event_store import append_event

from operator_governance.authority_escalation import (
    AuthorityEscalationGuard,
    get_authority_escalation_guard,
)
from operator_governance.consent_router import (
    ConsentRouter,
    get_consent_router,
)
from operator_governance.governance_visibility import (
    GovernanceVisibilityMonitor,
    get_governance_visibility_monitor,
)
from operator_governance.manual_lockout import (
    ManualLockoutGuard,
    get_manual_lockout_guard,
)
from operator_governance.operator_constitution import (
    OperatorConstitution,
    get_operator_constitution,
)
from operator_governance.override_priority import (
    OverridePriorityManager,
    get_override_priority_manager,
)


class OperatorGovernanceEngine:
    """
    Central coordinator for operator sovereignty.

    Thread-safe. Holds lazy references to all 5 guards.
    Provides check_all() for a full governance snapshot and
    is_execution_allowed() as the execution gate.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_status_ts: int = 0
        self._status_interval_ns: int = 60 * 1_000_000_000  # 60 seconds

        # Lazy guard references
        self._constitution: OperatorConstitution | None = None
        self._override_mgr: OverridePriorityManager | None = None
        self._escalation_guard: AuthorityEscalationGuard | None = None
        self._lockout_guard: ManualLockoutGuard | None = None
        self._consent_router: ConsentRouter | None = None
        self._visibility_monitor: GovernanceVisibilityMonitor | None = None

    # ------------------------------------------------------------------
    # Guard properties
    # ------------------------------------------------------------------

    @property
    def constitution(self) -> OperatorConstitution:
        if self._constitution is None:
            self._constitution = get_operator_constitution()
        return self._constitution

    @property
    def override_mgr(self) -> OverridePriorityManager:
        if self._override_mgr is None:
            self._override_mgr = get_override_priority_manager()
        return self._override_mgr

    @property
    def escalation_guard(self) -> AuthorityEscalationGuard:
        if self._escalation_guard is None:
            self._escalation_guard = get_authority_escalation_guard()
        return self._escalation_guard

    @property
    def lockout_guard(self) -> ManualLockoutGuard:
        if self._lockout_guard is None:
            self._lockout_guard = get_manual_lockout_guard()
        return self._lockout_guard

    @property
    def consent_router(self) -> ConsentRouter:
        if self._consent_router is None:
            self._consent_router = get_consent_router()
        return self._consent_router

    @property
    def visibility_monitor(self) -> GovernanceVisibilityMonitor:
        if self._visibility_monitor is None:
            self._visibility_monitor = get_governance_visibility_monitor()
        return self._visibility_monitor

    # ------------------------------------------------------------------
    # Execution gate
    # ------------------------------------------------------------------

    def is_execution_allowed(self) -> bool:
        """
        Return True only if no lockout blocks execution.

        This is the single gate all execution paths must consult before
        placing any order. The operator controls this gate entirely.
        """
        return not self.lockout_guard.is_locked(
            LockoutScope.EXECUTION
        ) and not self.lockout_guard.is_locked(LockoutScope.ALL)

    def is_learning_allowed(self) -> bool:
        """Return True only if no lockout blocks learning."""
        return not self.lockout_guard.is_locked(
            LockoutScope.LEARNING
        ) and not self.lockout_guard.is_locked(LockoutScope.ALL)

    def is_autonomous_ops_allowed(self) -> bool:
        """Return True only if no lockout blocks autonomous operations."""
        return not self.lockout_guard.is_locked(
            LockoutScope.AUTONOMOUS_OPS
        ) and not self.lockout_guard.is_locked(LockoutScope.ALL)

    # ------------------------------------------------------------------
    # Unified health check
    # ------------------------------------------------------------------

    def check_all(self) -> OperatorGovernanceStatus:
        """
        Aggregate operator governance health snapshot.

        Queries each guard without triggering new violation events.
        """
        ts_ns = _time.time_ns()

        # Authority integrity
        authority_intact = self.constitution.violation_count() == 0

        # No unauthorized escalation
        no_unauthorized_escalation = self.escalation_guard.pending_count() == 0

        # No active lockout breach (any active lockout is operator-issued —
        # it's not a "breach" per se, but callers need to know it's active)
        no_active_lockout_breach = not self.lockout_guard.is_any_locked()

        # Consent backlog
        consent_backlog = self.consent_router.pending_count()

        # Visibility health
        unhealthy = self.visibility_monitor.unhealthy_subsystems()
        visibility_healthy = len(unhealthy) == 0

        # Active overrides
        active_overrides = self.override_mgr.override_count()

        overall_healthy = (
            authority_intact
            and no_unauthorized_escalation
            and visibility_healthy
        )

        detail_parts: list[str] = []
        if not authority_intact:
            detail_parts.append(
                f"constitution_violations={self.constitution.violation_count()}"
            )
        if not no_unauthorized_escalation:
            detail_parts.append(
                f"escalation_pending={self.escalation_guard.pending_count()}"
            )
        if consent_backlog > 0:
            detail_parts.append(f"consent_backlog={consent_backlog}")
        if not visibility_healthy:
            detail_parts.append(f"invisible_subsystems={unhealthy}")
        if not no_active_lockout_breach:
            detail_parts.append("lockout_active")
        detail = "; ".join(detail_parts) if detail_parts else "all guards healthy"

        return OperatorGovernanceStatus(
            ts_ns=ts_ns,
            overall_healthy=overall_healthy,
            authority_intact=authority_intact,
            no_unauthorized_escalation=no_unauthorized_escalation,
            no_active_lockout_breach=no_active_lockout_breach,
            consent_backlog=consent_backlog,
            visibility_healthy=visibility_healthy,
            active_overrides=active_overrides,
            detail=detail,
        )

    # ------------------------------------------------------------------
    # Periodic status emission
    # ------------------------------------------------------------------

    def emit_status(self) -> OperatorGovernanceStatus:
        """
        Compute and emit OPGOV_STATUS to the governance ledger.

        Rate-limited to once per _status_interval_ns.
        """
        ts_ns = _time.time_ns()
        status = self.check_all()

        with self._lock:
            should_emit = (ts_ns - self._last_status_ts) >= self._status_interval_ns
            if should_emit:
                self._last_status_ts = ts_ns

        if should_emit:
            append_event(
                "GOVERNANCE",
                "OPGOV_STATUS",
                "operator_governance.engine",
                {
                    "overall_healthy": status.overall_healthy,
                    "authority_intact": status.authority_intact,
                    "no_unauthorized_escalation": status.no_unauthorized_escalation,
                    "no_active_lockout_breach": status.no_active_lockout_breach,
                    "consent_backlog": status.consent_backlog,
                    "visibility_healthy": status.visibility_healthy,
                    "active_overrides": status.active_overrides,
                    "detail": status.detail,
                },
            )

        return status

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        status = self.check_all()
        return {
            "status": {
                "overall_healthy": status.overall_healthy,
                "authority_intact": status.authority_intact,
                "no_unauthorized_escalation": status.no_unauthorized_escalation,
                "no_active_lockout_breach": status.no_active_lockout_breach,
                "consent_backlog": status.consent_backlog,
                "visibility_healthy": status.visibility_healthy,
                "active_overrides": status.active_overrides,
            },
            "constitution": self.constitution.snapshot(),
            "overrides": self.override_mgr.snapshot(),
            "escalation": self.escalation_guard.snapshot(),
            "lockouts": self.lockout_guard.snapshot(),
            "consent": self.consent_router.snapshot(),
            "visibility": self.visibility_monitor.snapshot(),
        }


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: OperatorGovernanceEngine | None = None
_lock = threading.Lock()


def get_operator_governance() -> OperatorGovernanceEngine:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = OperatorGovernanceEngine()
    return _instance


__all__ = ["OperatorGovernanceEngine", "get_operator_governance"]

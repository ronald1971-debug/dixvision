"""
system_governance/engine.py
DIX VISION v42.2 — System Governance Engine

Central coordinator for runtime structural integrity. Delegates to the
6 specialist guards, aggregates their state into SystemGovernanceStatus,
and emits periodic SYSGOV_STATUS events to the governance ledger.

Responsibilities:
  - Hold lazy references to all 6 guards
  - Provide check_all() → SystemGovernanceStatus
  - Emit SYSGOV_STATUS periodically (default: every 60 seconds)

System governance is P4 during development phases (lowest priority —
cognitive integrity comes first) and P4 during live deployment.
It never executes trades. It never modifies subsystem state directly.
It observes and reports.
"""

from __future__ import annotations

import threading
import time as _time
from typing import Any

from core.contracts.system_governance import SystemGovernanceStatus
from state.ledger.event_store import append_event

from system_governance.contract_integrity import (
    ContractIntegrityGuard,
    get_contract_integrity_guard,
)
from system_governance.convergence_monitor import (
    ConvergenceMonitor,
    get_convergence_monitor,
)
from system_governance.dependency_validator import (
    DependencyValidator,
    get_dependency_validator,
)
from system_governance.replay_integrity import (
    ReplayIntegrityGuard,
    get_replay_integrity_guard,
)
from system_governance.runtime_consistency import (
    RuntimeConsistencyMonitor,
    get_runtime_consistency_monitor,
)
from system_governance.topology_guard import (
    TopologyGuard,
    get_topology_guard,
)


class SystemGovernanceEngine:
    """
    Central coordinator for all system integrity guards.

    Thread-safe. Holds lazy references to all 6 specialist guards.
    Provides check_all() for a full structural integrity snapshot.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_status_ts: int = 0
        self._status_interval_ns: int = 60 * 1_000_000_000  # 60 seconds

        self._contract_integrity: ContractIntegrityGuard | None = None
        self._topology_guard: TopologyGuard | None = None
        self._runtime_consistency: RuntimeConsistencyMonitor | None = None
        self._replay_integrity: ReplayIntegrityGuard | None = None
        self._convergence_monitor: ConvergenceMonitor | None = None
        self._dependency_validator: DependencyValidator | None = None

    # ------------------------------------------------------------------
    # Guard properties
    # ------------------------------------------------------------------

    @property
    def contract_integrity(self) -> ContractIntegrityGuard:
        if self._contract_integrity is None:
            self._contract_integrity = get_contract_integrity_guard()
        return self._contract_integrity

    @property
    def topology_guard(self) -> TopologyGuard:
        if self._topology_guard is None:
            self._topology_guard = get_topology_guard()
        return self._topology_guard

    @property
    def runtime_consistency(self) -> RuntimeConsistencyMonitor:
        if self._runtime_consistency is None:
            self._runtime_consistency = get_runtime_consistency_monitor()
        return self._runtime_consistency

    @property
    def replay_integrity(self) -> ReplayIntegrityGuard:
        if self._replay_integrity is None:
            self._replay_integrity = get_replay_integrity_guard()
        return self._replay_integrity

    @property
    def convergence_monitor(self) -> ConvergenceMonitor:
        if self._convergence_monitor is None:
            self._convergence_monitor = get_convergence_monitor()
        return self._convergence_monitor

    @property
    def dependency_validator(self) -> DependencyValidator:
        if self._dependency_validator is None:
            self._dependency_validator = get_dependency_validator()
        return self._dependency_validator

    # ------------------------------------------------------------------
    # Unified health check
    # ------------------------------------------------------------------

    def check_all(self) -> SystemGovernanceStatus:
        """
        Aggregate system governance health snapshot.

        Queries each guard without triggering new violation events.
        """
        ts_ns = _time.time_ns()

        contracts_healthy = self.contract_integrity.violation_count() == 0
        topology_clean = self.topology_guard.violation_count() == 0
        replay_deterministic = self.replay_integrity.violation_count() == 0
        convergence_score = self.convergence_monitor.overall_convergence_score()
        consistency_ok = len(self.runtime_consistency.failing_checks()) == 0
        dependencies_valid = self.dependency_validator.violation_count() == 0

        active_violations = (
            self.contract_integrity.violation_count()
            + self.topology_guard.violation_count()
            + self.replay_integrity.violation_count()
            + self.runtime_consistency.violation_count()
            + self.dependency_validator.violation_count()
        )

        overall_healthy = (
            contracts_healthy
            and topology_clean
            and replay_deterministic
            and consistency_ok
            and dependencies_valid
        )

        detail_parts: list[str] = []
        if not contracts_healthy:
            detail_parts.append(
                f"contract_violations={self.contract_integrity.violation_count()}"
            )
        if not topology_clean:
            detail_parts.append(
                f"topology_violations={self.topology_guard.violation_count()}"
            )
        if not replay_deterministic:
            detail_parts.append(
                f"replay_violations={self.replay_integrity.violation_count()}"
            )
        if not consistency_ok:
            detail_parts.append(
                f"consistency_failing={self.runtime_consistency.failing_checks()}"
            )
        if not dependencies_valid:
            detail_parts.append(
                f"dep_violations={self.dependency_validator.violation_count()}"
            )
        if convergence_score < 1.0:
            detail_parts.append(f"convergence={convergence_score:.2f}")
        detail = "; ".join(detail_parts) if detail_parts else "all guards healthy"

        return SystemGovernanceStatus(
            ts_ns=ts_ns,
            overall_healthy=overall_healthy,
            contracts_healthy=contracts_healthy,
            topology_clean=topology_clean,
            replay_deterministic=replay_deterministic,
            convergence_score=convergence_score,
            consistency_ok=consistency_ok,
            dependencies_valid=dependencies_valid,
            active_violations=active_violations,
            detail=detail,
        )

    # ------------------------------------------------------------------
    # Periodic status emission
    # ------------------------------------------------------------------

    def emit_status(self) -> SystemGovernanceStatus:
        """
        Compute and emit SYSGOV_STATUS to the governance ledger.

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
                "SYSGOV_STATUS",
                "system_governance.engine",
                {
                    "overall_healthy": status.overall_healthy,
                    "contracts_healthy": status.contracts_healthy,
                    "topology_clean": status.topology_clean,
                    "replay_deterministic": status.replay_deterministic,
                    "convergence_score": status.convergence_score,
                    "consistency_ok": status.consistency_ok,
                    "dependencies_valid": status.dependencies_valid,
                    "active_violations": status.active_violations,
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
                "contracts_healthy": status.contracts_healthy,
                "topology_clean": status.topology_clean,
                "replay_deterministic": status.replay_deterministic,
                "convergence_score": status.convergence_score,
                "consistency_ok": status.consistency_ok,
                "dependencies_valid": status.dependencies_valid,
                "active_violations": status.active_violations,
            },
            "contract_integrity": self.contract_integrity.snapshot(),
            "topology": self.topology_guard.snapshot(),
            "replay": self.replay_integrity.snapshot(),
            "convergence": self.convergence_monitor.snapshot(),
            "consistency": self.runtime_consistency.snapshot(),
            "dependencies": self.dependency_validator.snapshot(),
        }


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: SystemGovernanceEngine | None = None
_lock = threading.Lock()


def get_system_governance() -> SystemGovernanceEngine:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = SystemGovernanceEngine()
    return _instance


__all__ = ["SystemGovernanceEngine", "get_system_governance"]

"""
system_governance/runtime_consistency.py
DIX VISION v42.2 — Runtime Consistency Monitor

Shared state must remain consistent across subsystems. When two
subsystems hold different views of the same datum (e.g. current mode,
position size, risk budget), the system is in an inconsistent state
and decisions may be made on stale or contradictory data.

This monitor accepts consistency check results from subsystems and
aggregates them into RuntimeConsistencyReport records. Inconsistencies
above the warning threshold are escalated to the ledger.
"""

from __future__ import annotations

import threading
import time as _time
from collections import deque
from typing import Any

from core.contracts.system_governance import (
    RuntimeConsistencyReport,
    SystemGovernanceSeverity,
)
from state.ledger.event_store import append_event


_MAX_HISTORY = 500
_INCONSISTENCY_WARN_COUNT = 3  # consecutive failures before HIGH severity


class RuntimeConsistencyMonitor:
    """
    Aggregates cross-subsystem state consistency check results.

    Thread-safe. Subsystems call record_check() with the outcome of their
    own consistency validation. The monitor tracks streaks and escalates
    severity when failures are consecutive.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reports: deque[RuntimeConsistencyReport] = deque(maxlen=_MAX_HISTORY)
        # check_name → consecutive failure count
        self._failure_streaks: dict[str, int] = {}
        self._violation_count: int = 0

    # ------------------------------------------------------------------
    # Check recording
    # ------------------------------------------------------------------

    def record_check(
        self,
        check_name: str,
        consistent: bool,
        divergent_subsystems: tuple[str, ...] = (),
        detail: str = "",
    ) -> RuntimeConsistencyReport:
        """
        Record the result of a runtime consistency check.

        Emits SYSGOV_CONSISTENCY_VIOLATION when consistent=False.
        Severity escalates to HIGH after _INCONSISTENCY_WARN_COUNT consecutive failures.
        """
        ts_ns = _time.time_ns()

        with self._lock:
            if consistent:
                self._failure_streaks.pop(check_name, None)
                severity = SystemGovernanceSeverity.INFO
            else:
                streak = self._failure_streaks.get(check_name, 0) + 1
                self._failure_streaks[check_name] = streak
                severity = (
                    SystemGovernanceSeverity.HIGH
                    if streak >= _INCONSISTENCY_WARN_COUNT
                    else SystemGovernanceSeverity.WARNING
                )
                self._violation_count += 1

        report = RuntimeConsistencyReport(
            ts_ns=ts_ns,
            check_name=check_name,
            consistent=consistent,
            divergent_subsystems=divergent_subsystems,
            severity=severity,
            detail=detail,
        )

        with self._lock:
            self._reports.append(report)

        if not consistent:
            append_event(
                "GOVERNANCE",
                "SYSGOV_CONSISTENCY_VIOLATION",
                "system_governance.runtime_consistency",
                {
                    "check_name": check_name,
                    "divergent_subsystems": list(divergent_subsystems),
                    "severity": severity.value,
                    "detail": detail,
                    "consecutive_failures": self._failure_streaks.get(check_name, 1),
                },
            )

        return report

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def is_consistent(self, check_name: str) -> bool:
        """Return True if the most recent check for check_name passed."""
        with self._lock:
            return self._failure_streaks.get(check_name, 0) == 0

    def failing_checks(self) -> list[str]:
        """Return check names that are currently failing."""
        with self._lock:
            return [k for k, v in self._failure_streaks.items() if v > 0]

    def violation_count(self) -> int:
        with self._lock:
            return self._violation_count

    def recent_reports(self, n: int = 20) -> list[RuntimeConsistencyReport]:
        with self._lock:
            items = list(self._reports)
        return items[-n:]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "violation_count": self._violation_count,
                "failing_checks": list(self._failure_streaks.keys()),
                "history_size": len(self._reports),
            }


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: RuntimeConsistencyMonitor | None = None
_lock = threading.Lock()


def get_runtime_consistency_monitor() -> RuntimeConsistencyMonitor:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = RuntimeConsistencyMonitor()
    return _instance


__all__ = ["RuntimeConsistencyMonitor", "get_runtime_consistency_monitor"]

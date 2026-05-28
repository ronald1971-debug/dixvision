"""
system_governance/convergence_monitor.py
DIX VISION v42.2 — Convergence Monitor

Tracks whether subsystems are converging toward full architectural
integration (INTEGRATED) or drifting apart (DIVERGING/STALLED).

A subsystem is considered fully integrated when it:
  1. Exposes typed inter-subsystem contracts
  2. Emits audit events to the governance ledger
  3. Has an observable state (snapshot() endpoint)
  4. Supports deterministic event replay (INV-15)
  5. Is visible to the operator

The integration_score (0.0–1.0) is the fraction of these 5 dimensions
currently satisfied. A score < 0.4 is DIVERGING; stalled if unchanged
for more than STALL_WINDOW_NS.
"""

from __future__ import annotations

import threading
import time as _time
from typing import Any

from core.contracts.system_governance import (
    ConvergenceRecord,
    ConvergenceState,
)
from state.ledger.event_store import append_event


STALL_WINDOW_NS = 3_600 * 1_000_000_000  # 1 hour without improvement = stalled
DIVERGING_THRESHOLD = 0.4


class ConvergenceMonitor:
    """
    Tracks and reports subsystem convergence toward architectural integration.

    Thread-safe. Subsystems self-report via update_subsystem().
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # subsystem → ConvergenceRecord (latest)
        self._records: dict[str, ConvergenceRecord] = {}
        # subsystem → (last_score, last_improvement_ts_ns)
        self._progress: dict[str, tuple[float, int]] = {}

    # ------------------------------------------------------------------
    # Subsystem registration / update
    # ------------------------------------------------------------------

    def update_subsystem(
        self,
        subsystem: str,
        has_contracts: bool,
        emits_audit_events: bool,
        observable: bool,
        supports_replay: bool,
        operator_visible: bool,
        detail: str = "",
    ) -> ConvergenceRecord:
        """
        Record the current integration state of a subsystem.

        Computes integration_score and ConvergenceState, emits
        SYSGOV_CONVERGENCE_STALLED if stalled.
        """
        ts_ns = _time.time_ns()

        # Integration score: fraction of 5 dimensions satisfied
        dimensions = [
            has_contracts,
            emits_audit_events,
            observable,
            supports_replay,
            operator_visible,
        ]
        score = sum(1 for d in dimensions if d) / len(dimensions)

        # Determine convergence state
        with self._lock:
            prev_score, last_improvement_ts = self._progress.get(
                subsystem, (0.0, ts_ns)
            )
            if score > prev_score:
                last_improvement_ts = ts_ns
            self._progress[subsystem] = (score, last_improvement_ts)
            time_since_improvement = ts_ns - last_improvement_ts

        if score >= 1.0:
            state = ConvergenceState.INTEGRATED
        elif score < DIVERGING_THRESHOLD:
            state = ConvergenceState.DIVERGING
        elif time_since_improvement > STALL_WINDOW_NS:
            state = ConvergenceState.STALLED
        else:
            state = ConvergenceState.CONVERGING

        record = ConvergenceRecord(
            ts_ns=ts_ns,
            subsystem=subsystem,
            state=state,
            has_contracts=has_contracts,
            emits_audit_events=emits_audit_events,
            observable=observable,
            supports_replay=supports_replay,
            operator_visible=operator_visible,
            integration_score=score,
            detail=detail,
        )

        with self._lock:
            self._records[subsystem] = record

        if state in (ConvergenceState.STALLED, ConvergenceState.DIVERGING):
            append_event(
                "GOVERNANCE",
                "SYSGOV_CONVERGENCE_STALLED",
                "system_governance.convergence_monitor",
                {
                    "subsystem": subsystem,
                    "state": state.value,
                    "integration_score": score,
                    "detail": detail,
                },
            )

        return record

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def overall_convergence_score(self) -> float:
        """
        Mean integration score across all tracked subsystems.

        Returns 1.0 when no subsystems have been registered yet.
        """
        with self._lock:
            records = list(self._records.values())
        if not records:
            return 1.0
        return sum(r.integration_score for r in records) / len(records)

    def diverging_subsystems(self) -> list[str]:
        with self._lock:
            return [
                s
                for s, r in self._records.items()
                if r.state in (ConvergenceState.DIVERGING, ConvergenceState.STALLED)
            ]

    def get_record(self, subsystem: str) -> ConvergenceRecord | None:
        with self._lock:
            return self._records.get(subsystem)

    def all_records(self) -> dict[str, ConvergenceRecord]:
        with self._lock:
            return dict(self._records)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            records = dict(self._records)
        return {
            "subsystem_count": len(records),
            "overall_score": self.overall_convergence_score(),
            "diverging": [
                s
                for s, r in records.items()
                if r.state in (ConvergenceState.DIVERGING, ConvergenceState.STALLED)
            ],
            "integrated": [
                s for s, r in records.items() if r.state is ConvergenceState.INTEGRATED
            ],
        }


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: ConvergenceMonitor | None = None
_lock = threading.Lock()


def get_convergence_monitor() -> ConvergenceMonitor:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = ConvergenceMonitor()
    return _instance


__all__ = ["ConvergenceMonitor", "get_convergence_monitor"]

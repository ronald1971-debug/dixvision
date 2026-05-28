"""
operator_governance/governance_visibility.py
DIX VISION v42.2 — Governance Visibility Monitor

All governance actions must remain visible to the operator at all times.
This monitor tracks, per subsystem, whether the expected number of
governance events is actually reaching the ledger.

A subsystem with visibility_score < VISIBILITY_WARNING_THRESHOLD is
flagged as potentially suppressing its governance output — a
constitutional violation.

Invariants:
  - Suppression of governance events is a constitutional violation.
  - visibility_score = events_visible / events_expected (0.0–1.0).
  - Scores are rolling over the last WINDOW_SIZE events per subsystem.
"""

from __future__ import annotations

import threading
import time as _time
from collections import deque
from typing import Any

from core.contracts.operator_governance import VisibilityRecord
from state.ledger.event_store import append_event


VISIBILITY_WARNING_THRESHOLD = 0.80
VISIBILITY_CRITICAL_THRESHOLD = 0.50
WINDOW_SIZE = 100


class GovernanceVisibilityMonitor:
    """
    Tracks whether each subsystem is emitting its governance events.

    Thread-safe. Callers use record_expected() when an event should be
    emitted and record_visible() when it actually arrives. The ratio
    drives the VisibilityRecord.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # subsystem → deque of (expected: bool) over rolling WINDOW_SIZE
        # True = expected-and-received, False = expected-but-missed
        self._windows: dict[str, deque[bool]] = {}
        # subsystem → count of suppressed events (expected but never seen)
        self._suppressed: dict[str, int] = {}
        self._total_violations: int = 0

    # ------------------------------------------------------------------
    # Event recording
    # ------------------------------------------------------------------

    def record_expected(self, subsystem: str) -> None:
        """
        Record that a governance event is expected from a subsystem.

        Call this when a governance action occurs that should produce a
        ledger event. If record_visible() is not called within the same
        window slot, it counts as suppressed.
        """
        with self._lock:
            window = self._windows.setdefault(
                subsystem, deque(maxlen=WINDOW_SIZE)
            )
            window.append(False)  # pending — not yet seen as visible
            self._suppressed.setdefault(subsystem, 0)

    def record_visible(self, subsystem: str) -> None:
        """
        Record that a governance event was observed from a subsystem.

        Flips the most recent False slot to True (event seen). If there
        is no pending False slot, the observation is recorded as a bonus
        visible event (score improves).
        """
        with self._lock:
            window = self._windows.setdefault(
                subsystem, deque(maxlen=WINDOW_SIZE)
            )
            # Find the rightmost False slot and flip it
            items = list(window)
            for i in range(len(items) - 1, -1, -1):
                if not items[i]:
                    items[i] = True
                    # Rebuild the deque with updated values
                    new_window: deque[bool] = deque(items, maxlen=WINDOW_SIZE)
                    self._windows[subsystem] = new_window
                    return
            # No pending slot — add a new visible entry
            window.append(True)

    # ------------------------------------------------------------------
    # Scoring and reporting
    # ------------------------------------------------------------------

    def score(self, subsystem: str) -> float:
        """
        Return the current visibility score for a subsystem (0.0–1.0).

        1.0 = all expected events are visible; 0.0 = nothing visible.
        Returns 1.0 for unknown subsystems (benefit of the doubt until
        they start emitting).
        """
        with self._lock:
            window = self._windows.get(subsystem)
            if not window:
                return 1.0
            items = list(window)
        if not items:
            return 1.0
        return sum(items) / len(items)

    def get_record(self, subsystem: str) -> VisibilityRecord:
        """
        Compute and return a VisibilityRecord for a subsystem.

        Emits OPGOV_VISIBILITY_DEGRADED to the ledger if score is below
        the warning threshold.
        """
        ts_ns = _time.time_ns()

        with self._lock:
            window = self._windows.get(subsystem, deque())
            items = list(window)
            suppressed = self._suppressed.get(subsystem, 0)

        events_expected = len(items)
        events_visible = sum(items)
        visibility_score = (
            events_visible / events_expected if events_expected > 0 else 1.0
        )
        healthy = visibility_score >= VISIBILITY_WARNING_THRESHOLD

        record = VisibilityRecord(
            subsystem=subsystem,
            ts_ns=ts_ns,
            events_expected=events_expected,
            events_visible=events_visible,
            visibility_score=visibility_score,
            suppressed_count=suppressed,
            healthy=healthy,
        )

        if not healthy:
            with self._lock:
                self._total_violations += 1
            append_event(
                "GOVERNANCE",
                "OPGOV_VISIBILITY_DEGRADED",
                "operator_governance.governance_visibility",
                {
                    "subsystem": subsystem,
                    "visibility_score": visibility_score,
                    "events_expected": events_expected,
                    "events_visible": events_visible,
                    "suppressed_count": suppressed,
                    "severity": (
                        "CRITICAL"
                        if visibility_score < VISIBILITY_CRITICAL_THRESHOLD
                        else "WARNING"
                    ),
                },
            )

        return record

    def all_scores(self) -> dict[str, float]:
        """Return visibility scores for all tracked subsystems."""
        with self._lock:
            subsystems = list(self._windows.keys())
        return {s: self.score(s) for s in subsystems}

    def unhealthy_subsystems(self) -> list[str]:
        """Return subsystems with score below WARNING threshold."""
        return [s for s, sc in self.all_scores().items() if sc < VISIBILITY_WARNING_THRESHOLD]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            total_violations = self._total_violations

        scores = self.all_scores()
        return {
            "subsystem_count": len(scores),
            "unhealthy_count": sum(
                1 for sc in scores.values() if sc < VISIBILITY_WARNING_THRESHOLD
            ),
            "total_visibility_violations": total_violations,
            "scores": scores,
        }


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: GovernanceVisibilityMonitor | None = None
_lock = threading.Lock()


def get_governance_visibility_monitor() -> GovernanceVisibilityMonitor:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = GovernanceVisibilityMonitor()
    return _instance


__all__ = ["GovernanceVisibilityMonitor", "get_governance_visibility_monitor"]

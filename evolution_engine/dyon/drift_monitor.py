"""evolution_engine.dyon.drift_monitor — ArchitectureDriftMonitor.

Tracks violation counts across topology scans over time and computes:

  health_score    — 0–100 reflecting current architectural integrity
  drift_trend     — IMPROVING | STABLE | DEGRADING (slope over last N scans)
  spike_detected  — True when violation count surges > threshold in one scan
  grade           — A / B / C / D / F letter-grade summary

Health score formula:
  base = 100
  deduct 15 per CRITICAL violation (capped at 60 deduction)
  deduct 5 per WARNING violation (capped at 30 deduction)
  health = max(0, base - critical_deduct - warning_deduct)

Drift trend: OLS slope over the last 20 scan health scores.
  slope > +0.5  → IMPROVING
  slope < -0.5  → DEGRADING
  else          → STABLE

Authority (L2/B1): evolution_engine.* and core.* only.
INV-15: ts_ns is caller-supplied; no wall-clock reads.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any

_logger = logging.getLogger(__name__)

_MAX_HISTORY: int = 100
_TREND_WINDOW: int = 20
_SPIKE_THRESHOLD: int = 3         # new violations vs previous scan
_GRADE_THRESHOLDS = (90, 75, 55, 35)   # A, B, C, D thresholds; below D → F


def _ols_slope(ys: list[float]) -> float:
    """Ordinary-least-squares slope for a y-sequence (x = index)."""
    n = len(ys)
    if n < 2:
        return 0.0
    x_bar = (n - 1) / 2.0
    y_bar = sum(ys) / n
    num = sum((i - x_bar) * (yi - y_bar) for i, yi in enumerate(ys))
    den = sum((i - x_bar) ** 2 for i in range(n))
    return num / den if den != 0.0 else 0.0


# ---------------------------------------------------------------------------
# Per-scan data point
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ScanDataPoint:
    """One scan's summary for the drift time series."""

    ts_ns: int
    scan_index: int
    files_scanned: int
    critical_count: int
    warning_count: int
    health_score: float
    violation_keys: frozenset[str]   # for new-violation detection

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts_ns": self.ts_ns,
            "scan_index": self.scan_index,
            "files_scanned": self.files_scanned,
            "critical_count": self.critical_count,
            "warning_count": self.warning_count,
            "health_score": round(self.health_score, 1),
        }


# ---------------------------------------------------------------------------
# ArchitectureDriftMonitor
# ---------------------------------------------------------------------------


@dataclass
class DriftState:
    """Current drift assessment."""

    health_score: float = 100.0
    trend: str = "STABLE"          # IMPROVING | STABLE | DEGRADING
    grade: str = "A"
    spike_detected: bool = False
    new_violations_this_scan: int = 0
    resolved_violations_this_scan: int = 0
    scan_count: int = 0
    last_ts_ns: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "health_score": round(self.health_score, 1),
            "trend": self.trend,
            "grade": self.grade,
            "spike_detected": self.spike_detected,
            "new_violations_this_scan": self.new_violations_this_scan,
            "resolved_violations_this_scan": self.resolved_violations_this_scan,
            "scan_count": self.scan_count,
        }


class ArchitectureDriftMonitor:
    """Tracks architectural health over time from topology scan results.

    Feed each scan result via `record_scan()` after DyonRuntime.tick().
    Call `snapshot()` for operator dashboards and REST endpoints.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._history: deque[ScanDataPoint] = deque(maxlen=_MAX_HISTORY)
        self._state = DriftState()

    # ------------------------------------------------------------------
    # Record new scan
    # ------------------------------------------------------------------

    def record_scan(
        self,
        *,
        ts_ns: int,
        files_scanned: int,
        critical_count: int,
        warning_count: int,
        violations: list[dict[str, Any]],
    ) -> DriftState:
        """Record one topology scan result and recompute drift state.

        Args:
            violations: List of violation dicts with at least 'invariant_id'
                        and 'source_module' keys.

        Returns the updated DriftState snapshot.
        """
        health = self._compute_health(critical_count, warning_count)
        grade = self._health_to_grade(health)
        vkeys = frozenset(
            f"{v.get('invariant_id', '?')}:{v.get('source_module', '?')}"
            for v in violations
        )

        with self._lock:
            scan_idx = self._state.scan_count + 1
            point = ScanDataPoint(
                ts_ns=ts_ns,
                scan_index=scan_idx,
                files_scanned=files_scanned,
                critical_count=critical_count,
                warning_count=warning_count,
                health_score=health,
                violation_keys=vkeys,
            )

            # Compute new / resolved vs previous scan
            prev_vkeys = (
                self._history[-1].violation_keys if self._history else frozenset()
            )
            new_viol = len(vkeys - prev_vkeys)
            resolved = len(prev_vkeys - vkeys)
            spike = new_viol >= _SPIKE_THRESHOLD

            self._history.append(point)

            # Trend from last N health scores
            trend_scores = [p.health_score for p in self._history][-_TREND_WINDOW:]
            slope = _ols_slope(trend_scores)
            if slope > 0.5:
                trend = "IMPROVING"
            elif slope < -0.5:
                trend = "DEGRADING"
            else:
                trend = "STABLE"

            self._state = DriftState(
                health_score=health,
                trend=trend,
                grade=grade,
                spike_detected=spike,
                new_violations_this_scan=new_viol,
                resolved_violations_this_scan=resolved,
                scan_count=scan_idx,
                last_ts_ns=ts_ns,
            )
            state_copy = DriftState(
                health_score=self._state.health_score,
                trend=self._state.trend,
                grade=self._state.grade,
                spike_detected=self._state.spike_detected,
                new_violations_this_scan=self._state.new_violations_this_scan,
                resolved_violations_this_scan=self._state.resolved_violations_this_scan,
                scan_count=self._state.scan_count,
                last_ts_ns=self._state.last_ts_ns,
            )

        if spike:
            _logger.warning(
                "ArchitectureDriftMonitor: SPIKE detected — %d new violations (scan #%d)",
                new_viol, scan_idx,
            )
        return state_copy

    # ------------------------------------------------------------------
    # Read surface
    # ------------------------------------------------------------------

    def current_state(self) -> DriftState:
        with self._lock:
            return self._state

    def health_score(self) -> float:
        with self._lock:
            return self._state.health_score

    def trend(self) -> str:
        with self._lock:
            return self._state.trend

    def history_series(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent scan data points as JSON-serialisable list."""
        with self._lock:
            items = list(self._history)[-limit:]
        return [p.to_dict() for p in items]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            state = self._state.to_dict()
            series = [p.to_dict() for p in list(self._history)[-20:]]
        return {
            "runtime": "ArchitectureDriftMonitor",
            "current": state,
            "history_series": series,
            "history_depth": len(self._history),
        }

    def format_for_narrative(self) -> str:
        """Compact narrative fragment for consciousness stream."""
        with self._lock:
            s = self._state
        arrow = {"IMPROVING": "↑", "DEGRADING": "↓", "STABLE": "→"}.get(s.trend, "?")
        return (
            f"Architecture health {s.health_score:.0f}/100 (grade {s.grade}, trend {arrow})"
        )

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_health(critical: int, warning: int) -> float:
        crit_deduct = min(60.0, critical * 15.0)
        warn_deduct = min(30.0, warning * 5.0)
        return max(0.0, 100.0 - crit_deduct - warn_deduct)

    @staticmethod
    def _health_to_grade(score: float) -> str:
        a, b, c, d = _GRADE_THRESHOLDS
        if score >= a:
            return "A"
        if score >= b:
            return "B"
        if score >= c:
            return "C"
        if score >= d:
            return "D"
        return "F"


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_monitor: ArchitectureDriftMonitor | None = None
_monitor_lock = threading.Lock()


def get_drift_monitor() -> ArchitectureDriftMonitor:
    """Return the process-wide ArchitectureDriftMonitor singleton."""
    global _monitor
    with _monitor_lock:
        if _monitor is None:
            _monitor = ArchitectureDriftMonitor()
    return _monitor


__all__ = [
    "ArchitectureDriftMonitor",
    "DriftState",
    "ScanDataPoint",
    "get_drift_monitor",
]

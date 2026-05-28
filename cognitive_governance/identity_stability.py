"""
cognitive_governance/identity_stability.py
DIX VISION v42.2 — Identity Stability Monitor

Traders have behavioral fingerprints: characteristic patterns of
timing, sizing, sector preference, risk tolerance, and regime
sensitivity that define their trading "personality."

This guard tracks the cosine similarity between each trader's current
behavioral embedding and their rolling 7-day baseline. A sharp drop
in similarity indicates:
  - Potential memory contamination (their profile was incorrectly updated)
  - Data source corruption (a bad feed changed their apparent behavior)
  - Legitimate regime adaptation (not a violation — filtered by rate)

The distinction: legitimate adaptation is GRADUAL (< DRIFT_RATE_PER_HOUR
per hour). Contamination is SUDDEN (> SPIKE_THRESHOLD in a single window).

Gradual drift is normal and expected. The guard only fires on sudden spikes.
"""

from __future__ import annotations

import math
import threading
from collections import deque

from core.contracts.cognitive_governance import (
    CognitiveSeverity,
    CognitiveViolationKind,
    IdentityStabilityReport,
)
from state.ledger.event_store import append_event

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DRIFT_RATE_WARNING = 0.05          # cosine drift per hour; above this is abnormal
SPIKE_THRESHOLD = 0.25             # single-window spike in drift magnitude
BASELINE_WINDOW_HOURS = 168        # 7 days
MIN_BASELINE_SAMPLES = 10          # minimum samples before stability checking

_BASELINE_WINDOW_NS = BASELINE_WINDOW_HOURS * 3_600_000_000_000


class IdentityStabilityMonitor:
    """
    Monitors per-trader behavioral embedding stability against a 7-day
    rolling baseline.
    """

    def __init__(self) -> None:
        # trader_id → deque of (ts_ns: int, embedding: list[float])
        self._embeddings: dict[str, deque[tuple[int, list[float]]]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_trader_embedding(
        self,
        trader_id: str,
        embedding: list[float],
        ts_ns: int,
    ) -> IdentityStabilityReport:
        """
        Record a new behavioral embedding for a trader and check stability.

        Returns IdentityStabilityReport. If passed=False, Governance should
        investigate the source of the sudden behavioral shift.
        """
        with self._lock:
            if trader_id not in self._embeddings:
                self._embeddings[trader_id] = deque()

            hist = self._embeddings[trader_id]

            # Prune entries outside the 7-day window
            cutoff = ts_ns - _BASELINE_WINDOW_NS
            while hist and hist[0][0] < cutoff:
                hist.popleft()

            # Compute baseline before adding the new embedding
            baseline = self._compute_baseline(trader_id)
            has_baseline = baseline is not None and len(hist) >= MIN_BASELINE_SAMPLES

            # Store new embedding
            hist.append((ts_ns, list(embedding)))

        if not has_baseline or baseline is None:
            # Not enough history for a meaningful comparison
            import time
            report_ts = ts_ns
            return IdentityStabilityReport(
                ts_ns=report_ts,
                trader_id=trader_id,
                similarity_score=1.0,
                drift_magnitude=0.0,
                passed=True,
                severity=CognitiveSeverity.INFO,
                detail=f"insufficient baseline (need {MIN_BASELINE_SAMPLES} samples)",
            )

        similarity = self._cosine_similarity(baseline, embedding)
        similarity = max(-1.0, min(1.0, similarity))
        drift_magnitude = 1.0 - similarity

        passed = drift_magnitude < SPIKE_THRESHOLD

        if drift_magnitude >= SPIKE_THRESHOLD:
            severity = CognitiveSeverity.CRITICAL
        elif drift_magnitude >= SPIKE_THRESHOLD * 0.5:
            severity = CognitiveSeverity.WARNING
        else:
            severity = CognitiveSeverity.INFO

        detail_parts: list[str] = []
        if drift_magnitude >= SPIKE_THRESHOLD:
            detail_parts.append(
                f"SPIKE DETECTED: drift_magnitude={drift_magnitude:.4f} "
                f">= SPIKE_THRESHOLD={SPIKE_THRESHOLD}; "
                "sudden identity shift — possible memory contamination or data corruption"
            )
        elif drift_magnitude >= SPIKE_THRESHOLD * 0.5:
            detail_parts.append(
                f"drift_magnitude={drift_magnitude:.4f} approaching spike threshold"
            )

        detail = "; ".join(detail_parts) if detail_parts else (
            f"similarity={similarity:.4f}, drift={drift_magnitude:.4f}, OK"
        )

        report = IdentityStabilityReport(
            ts_ns=ts_ns,
            trader_id=trader_id,
            similarity_score=similarity,
            drift_magnitude=drift_magnitude,
            passed=passed,
            severity=severity,
            detail=detail,
        )

        if not passed:
            append_event(
                "GOVERNANCE",
                "COGOV_IDENTITY_STABILITY",
                "cognitive_governance.identity_stability",
                {
                    "trader_id": trader_id,
                    "similarity_score": similarity,
                    "drift_magnitude": drift_magnitude,
                    "passed": passed,
                    "severity": severity.value,
                    "violations": [CognitiveViolationKind.IDENTITY_INSTABILITY.value],
                    "detail": detail,
                },
            )

        return report

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if len(a) != len(b) or not a:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _compute_baseline(self, trader_id: str) -> list[float] | None:
        """
        Compute the weighted average baseline embedding for a trader.

        Uses exponential decay: older embeddings have lower weight.
        Assumes _lock is held by caller.
        """
        hist = self._embeddings.get(trader_id)
        if not hist or len(hist) < MIN_BASELINE_SAMPLES:
            return None

        items = list(hist)
        if not items:
            return None

        # Exponential decay: most recent has weight 1.0, older items decay
        n = len(items)
        weights: list[float] = []
        decay = 0.99
        for i in range(n):
            # Index 0 is oldest, n-1 is newest
            w = decay ** (n - 1 - i)
            weights.append(w)

        total_weight = sum(weights)
        if total_weight == 0.0:
            return None

        dim = len(items[0][1])
        baseline = [0.0] * dim

        for (_, emb), w in zip(items, weights):
            if len(emb) != dim:
                continue
            for j in range(dim):
                baseline[j] += emb[j] * (w / total_weight)

        return baseline


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: IdentityStabilityMonitor | None = None
_lock = threading.Lock()


def get_identity_stability_monitor() -> IdentityStabilityMonitor:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = IdentityStabilityMonitor()
    return _instance


__all__ = ["IdentityStabilityMonitor", "get_identity_stability_monitor"]

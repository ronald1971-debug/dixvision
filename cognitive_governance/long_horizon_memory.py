"""
cognitive_governance/long_horizon_memory.py
DIX VISION v42.2 — Long-Horizon Abstraction Memory

Tracks cognitive patterns across time windows of days to weeks, far beyond
the episodic memory range (seconds to hours). Captures slow-moving signals
that indicate structural changes in system cognition:

  - Trader behavioral drift (are decision patterns shifting over time?)
  - Strategy personality profiles (persistent signature of a strategy's behaviour)
  - Cognitive trend trajectories (is coherence improving or degrading over weeks?)
  - Regime adaptation quality (does the system correctly update to new regimes?)
  - Performance degradation signatures (are early warning patterns forming?)

Unlike short-horizon memory, long-horizon patterns are NOT discarded on
rolling windows. They accumulate until explicit retirement (pattern resolved
or superseded). The module enforces a maximum pattern count per subject to
prevent unbounded growth.

Governance integration:
  - Emits LongHorizonEvent records to the cognitive_governance ledger channel
  - Pattern DRIFTING state feeds into learning coherence (identity_stability dim)
  - Pattern DEGRADATION kind triggers WARN_OPERATOR via cognitive constitution

Thread-safe. Pure aggregation — no IO in hot path. INV-15 compliant for
deterministic pattern hashing.
"""

from __future__ import annotations

import hashlib
import math
import threading
import time as _time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PatternKind(StrEnum):
    BEHAVIORAL_DRIFT      = "BEHAVIORAL_DRIFT"        # Decision-making patterns shifting
    STRATEGY_PERSONALITY  = "STRATEGY_PERSONALITY"    # Stable strategy behavioural signature
    COGNITIVE_TREND       = "COGNITIVE_TREND"         # Multi-week coherence trajectory
    REGIME_ADAPTATION     = "REGIME_ADAPTATION"       # Quality of regime recognition updates
    PERFORMANCE_DEGRADATION = "PERFORMANCE_DEGRADATION"  # Slow-building failure signature
    REWARD_SHAPING_DRIFT  = "REWARD_SHAPING_DRIFT"    # Reward signal distribution change
    IDENTITY_EVOLUTION    = "IDENTITY_EVOLUTION"      # Controlled identity change over time


class PatternState(StrEnum):
    FORMING    = "FORMING"     # Insufficient observations to confirm
    ACTIVE     = "ACTIVE"      # Confirmed, currently observed
    DRIFTING   = "DRIFTING"    # Pattern is changing — attention required
    STABLE     = "STABLE"      # Pattern confirmed and unchanged for long window
    RETIRED    = "RETIRED"     # Pattern no longer observed; archived


class HorizonWindow(StrEnum):
    SHORT   = "SHORT"    # 1–24 hours
    MEDIUM  = "MEDIUM"   # 1–7 days
    LONG    = "LONG"     # 1–4 weeks
    EPOCH   = "EPOCH"    # > 4 weeks (structural baseline)


# ---------------------------------------------------------------------------
# Nanosecond duration constants
# ---------------------------------------------------------------------------

_NS_PER_HOUR  = 3_600_000_000_000
_NS_PER_DAY   = 86_400_000_000_000
_NS_PER_WEEK  = 7 * _NS_PER_DAY


def _horizon_for_span(span_ns: int) -> HorizonWindow:
    if span_ns < _NS_PER_DAY:
        return HorizonWindow.SHORT
    if span_ns < 7 * _NS_PER_DAY:
        return HorizonWindow.MEDIUM
    if span_ns < 28 * _NS_PER_DAY:
        return HorizonWindow.LONG
    return HorizonWindow.EPOCH


# ---------------------------------------------------------------------------
# Frozen dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PatternObservation:
    """A single timestamped data point contributing to a long-horizon pattern."""
    ts_ns: int
    value: float          # Normalised metric value [0, 1] where applicable
    context_hash: str     # MD5 of context dict (deterministic, INV-15)
    note: str = ""


@dataclass(frozen=True, slots=True)
class LongHorizonPattern:
    """
    A confirmed or forming long-horizon cognitive pattern.

    subject:       The entity this pattern belongs to (strategy ID, "system", "cognitive")
    pattern_id:    Deterministic: MD5(subject + kind + creation_ns)
    observations:  Ordered tuple of recent observations (capped at max_obs)
    confidence:    Weighted mean of recent observation values
    drift_rate:    Slope of confidence over recent observations (positive = improving)
    horizon:       Time window classification based on span
    """
    pattern_id: str
    subject: str
    kind: PatternKind
    state: PatternState
    first_observed_ns: int
    last_observed_ns: int
    occurrence_count: int
    confidence: float           # [0, 1]
    drift_rate: float           # per-week rate of change (positive = improving)
    horizon: HorizonWindow
    observations: tuple[PatternObservation, ...]
    summary: str = ""

    @property
    def span_ns(self) -> int:
        return max(0, self.last_observed_ns - self.first_observed_ns)

    @property
    def is_concerning(self) -> bool:
        """True if this pattern warrants operator attention."""
        return (
            (self.kind == PatternKind.BEHAVIORAL_DRIFT and self.drift_rate < -0.05)
            or (self.kind == PatternKind.PERFORMANCE_DEGRADATION and self.state == PatternState.ACTIVE)
            or (self.kind == PatternKind.COGNITIVE_TREND and self.confidence < 0.5)
            or (self.state == PatternState.DRIFTING and self.confidence < 0.6)
        )


@dataclass(frozen=True, slots=True)
class LongHorizonSnapshot:
    """Point-in-time snapshot of all active long-horizon patterns."""
    ts_ns: int
    total_patterns: int
    active_patterns: int
    drifting_patterns: int
    concerning_patterns: int
    weakest_confidence: float
    mean_confidence: float
    identity_stability_signal: float   # Feeds into LearningCoherenceMonitor
    detail: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pattern_id(subject: str, kind: PatternKind, creation_ns: int) -> str:
    raw = f"{subject}:{kind.value}:{creation_ns}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _context_hash(ctx: dict[str, Any]) -> str:
    canonical = ";".join(f"{k}={v}" for k, v in sorted(ctx.items()))
    return hashlib.md5(canonical.encode()).hexdigest()[:12]


def _weighted_confidence(obs: tuple[PatternObservation, ...], decay: float = 0.92) -> float:
    """Exponentially-weighted mean; most-recent observations have highest weight."""
    if not obs:
        return 0.5
    total_w = 0.0
    total_wv = 0.0
    w = 1.0
    for o in reversed(obs):
        total_wv += w * o.value
        total_w += w
        w *= decay
    return total_wv / total_w if total_w > 0 else 0.5


def _drift_rate(obs: tuple[PatternObservation, ...]) -> float:
    """
    Estimate per-week rate-of-change via linear regression slope.
    Returns 0.0 if fewer than 3 observations.
    """
    if len(obs) < 3:
        return 0.0
    n = len(obs)
    t0 = obs[0].ts_ns
    xs = [(o.ts_ns - t0) / _NS_PER_WEEK for o in obs]
    ys = [o.value for o in obs]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    den = sum((xs[i] - mean_x) ** 2 for i in range(n))
    return num / den if den > 1e-9 else 0.0


def _classify_state(
    current: PatternState,
    confidence: float,
    drift_rate: float,
    occurrence_count: int,
) -> PatternState:
    if current == PatternState.RETIRED:
        return PatternState.RETIRED
    if occurrence_count < 3:
        return PatternState.FORMING
    if abs(drift_rate) > 0.10:
        return PatternState.DRIFTING
    if confidence >= 0.75 and abs(drift_rate) < 0.02:
        return PatternState.STABLE
    return PatternState.ACTIVE


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class LongHorizonMemoryStore:
    """
    Thread-safe store for long-horizon cognitive patterns.

    Indexed by (subject, kind) pair. Each (subject, kind) can hold at most
    one live pattern; a new observation either updates the existing pattern
    or creates a new one if the previous was RETIRED.

    Maximum _MAX_PER_SUBJECT patterns per subject (excess retire oldest STABLE).
    """

    _MAX_PER_SUBJECT = 20
    _MAX_OBS_PER_PATTERN = 500

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # key: (subject, kind) → LongHorizonPattern
        self._patterns: dict[tuple[str, PatternKind], LongHorizonPattern] = {}
        # subject → list of pattern_ids (for capacity tracking)
        self._subject_index: dict[str, list[str]] = {}

    # ------------------------------------------------------------------
    # Observation ingestion
    # ------------------------------------------------------------------

    def observe(
        self,
        subject: str,
        kind: PatternKind,
        value: float,
        ts_ns: int | None = None,
        context: dict[str, Any] | None = None,
        note: str = "",
    ) -> LongHorizonPattern:
        """
        Record a new observation for (subject, kind).

        Creates the pattern if it doesn't exist; updates if it does.
        Returns the updated (or created) pattern.
        """
        ts_ns = ts_ns or _time.time_ns()
        ctx_hash = _context_hash(context or {})
        obs = PatternObservation(ts_ns=ts_ns, value=max(0.0, min(1.0, value)),
                                 context_hash=ctx_hash, note=note)

        with self._lock:
            key = (subject, kind)
            existing = self._patterns.get(key)

            if existing is None or existing.state == PatternState.RETIRED:
                pat = self._create(subject, kind, obs, ts_ns)
            else:
                pat = self._update(existing, obs)

            self._patterns[key] = pat
            self._track_subject(subject, pat.pattern_id)

        return pat

    def _create(
        self,
        subject: str,
        kind: PatternKind,
        obs: PatternObservation,
        ts_ns: int,
    ) -> LongHorizonPattern:
        pid = _pattern_id(subject, kind, ts_ns)
        return LongHorizonPattern(
            pattern_id=pid,
            subject=subject,
            kind=kind,
            state=PatternState.FORMING,
            first_observed_ns=ts_ns,
            last_observed_ns=ts_ns,
            occurrence_count=1,
            confidence=obs.value,
            drift_rate=0.0,
            horizon=HorizonWindow.SHORT,
            observations=(obs,),
        )

    def _update(
        self,
        pat: LongHorizonPattern,
        obs: PatternObservation,
    ) -> LongHorizonPattern:
        new_obs = pat.observations[-self._MAX_OBS_PER_PATTERN + 1:] + (obs,)
        confidence = _weighted_confidence(new_obs)
        dr = _drift_rate(new_obs)
        count = pat.occurrence_count + 1
        span = obs.ts_ns - pat.first_observed_ns
        horizon = _horizon_for_span(span)
        state = _classify_state(pat.state, confidence, dr, count)

        return LongHorizonPattern(
            pattern_id=pat.pattern_id,
            subject=pat.subject,
            kind=pat.kind,
            state=state,
            first_observed_ns=pat.first_observed_ns,
            last_observed_ns=obs.ts_ns,
            occurrence_count=count,
            confidence=confidence,
            drift_rate=dr,
            horizon=horizon,
            observations=new_obs,
            summary=pat.summary,
        )

    def _track_subject(self, subject: str, pattern_id: str) -> None:
        ids = self._subject_index.setdefault(subject, [])
        if pattern_id not in ids:
            ids.append(pattern_id)
        # If over capacity, retire oldest STABLE patterns
        if len(ids) > self._MAX_PER_SUBJECT:
            self._retire_oldest_stable(subject)

    def _retire_oldest_stable(self, subject: str) -> None:
        # Find oldest STABLE pattern for this subject and retire it
        stable_keys = [
            k for k, p in self._patterns.items()
            if k[0] == subject and p.state == PatternState.STABLE
        ]
        if not stable_keys:
            return
        oldest_key = min(stable_keys, key=lambda k: self._patterns[k].first_observed_ns)
        old = self._patterns[oldest_key]
        self._patterns[oldest_key] = LongHorizonPattern(
            pattern_id=old.pattern_id,
            subject=old.subject,
            kind=old.kind,
            state=PatternState.RETIRED,
            first_observed_ns=old.first_observed_ns,
            last_observed_ns=old.last_observed_ns,
            occurrence_count=old.occurrence_count,
            confidence=old.confidence,
            drift_rate=old.drift_rate,
            horizon=old.horizon,
            observations=old.observations,
            summary=old.summary,
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, subject: str, kind: PatternKind) -> LongHorizonPattern | None:
        with self._lock:
            return self._patterns.get((subject, kind))

    def patterns_for_subject(self, subject: str) -> list[LongHorizonPattern]:
        with self._lock:
            return [
                p for (s, _), p in self._patterns.items()
                if s == subject and p.state != PatternState.RETIRED
            ]

    def patterns_by_kind(self, kind: PatternKind) -> list[LongHorizonPattern]:
        with self._lock:
            return [
                p for (_, k), p in self._patterns.items()
                if k == kind and p.state != PatternState.RETIRED
            ]

    def concerning_patterns(self) -> list[LongHorizonPattern]:
        with self._lock:
            return [p for p in self._patterns.values() if p.is_concerning]

    def retire(self, subject: str, kind: PatternKind) -> None:
        with self._lock:
            key = (subject, kind)
            if key in self._patterns:
                old = self._patterns[key]
                self._patterns[key] = LongHorizonPattern(
                    pattern_id=old.pattern_id,
                    subject=old.subject,
                    kind=old.kind,
                    state=PatternState.RETIRED,
                    first_observed_ns=old.first_observed_ns,
                    last_observed_ns=old.last_observed_ns,
                    occurrence_count=old.occurrence_count,
                    confidence=old.confidence,
                    drift_rate=old.drift_rate,
                    horizon=old.horizon,
                    observations=old.observations,
                    summary=old.summary,
                )

    # ------------------------------------------------------------------
    # Aggregate signals
    # ------------------------------------------------------------------

    def identity_stability_signal(self) -> float:
        """
        Aggregate identity stability across IDENTITY_EVOLUTION and
        BEHAVIORAL_DRIFT patterns.

        Returns [0, 1]: 1.0 = fully stable, 0.0 = maximal drift.
        Used by LearningCoherenceMonitor.identity_stability dimension.
        """
        relevant: list[LongHorizonPattern] = []
        with self._lock:
            for p in self._patterns.values():
                if p.state == PatternState.RETIRED:
                    continue
                if p.kind in (PatternKind.IDENTITY_EVOLUTION, PatternKind.BEHAVIORAL_DRIFT):
                    relevant.append(p)
        if not relevant:
            return 1.0
        # Confidence near 1.0 for BEHAVIORAL_DRIFT means low drift (good)
        # Penalise patterns that are DRIFTING or have negative drift_rate
        scores: list[float] = []
        for p in relevant:
            base = p.confidence
            if p.state == PatternState.DRIFTING:
                base *= 0.7
            # Negative drift_rate means getting worse; cap penalty at 30%
            drift_penalty = max(0.0, min(0.3, -p.drift_rate))
            scores.append(max(0.0, base - drift_penalty))
        return min(1.0, sum(scores) / len(scores))

    def snapshot(self, ts_ns: int | None = None) -> LongHorizonSnapshot:
        ts_ns = ts_ns or _time.time_ns()
        with self._lock:
            active = [p for p in self._patterns.values()
                      if p.state not in (PatternState.RETIRED, PatternState.FORMING)]
        if not active:
            return LongHorizonSnapshot(
                ts_ns=ts_ns,
                total_patterns=len(self._patterns),
                active_patterns=0,
                drifting_patterns=0,
                concerning_patterns=0,
                weakest_confidence=1.0,
                mean_confidence=1.0,
                identity_stability_signal=1.0,
                detail="no_active_patterns",
            )

        drifting = sum(1 for p in active if p.state == PatternState.DRIFTING)
        concerning = sum(1 for p in active if p.is_concerning)
        confidences = [p.confidence for p in active]
        weakest = min(confidences)
        mean_conf = sum(confidences) / len(confidences)
        id_signal = self.identity_stability_signal()

        detail_parts: list[str] = []
        if drifting > 0:
            detail_parts.append(f"drifting={drifting}")
        if concerning > 0:
            detail_parts.append(f"concerning={concerning}")
        if weakest < 0.5:
            detail_parts.append(f"weakest_conf={weakest:.2f}")

        return LongHorizonSnapshot(
            ts_ns=ts_ns,
            total_patterns=len(self._patterns),
            active_patterns=len(active),
            drifting_patterns=drifting,
            concerning_patterns=concerning,
            weakest_confidence=weakest,
            mean_confidence=mean_conf,
            identity_stability_signal=id_signal,
            detail="; ".join(detail_parts) if detail_parts else f"mean_conf={mean_conf:.3f}",
        )

    def all_patterns(self, include_retired: bool = False) -> list[LongHorizonPattern]:
        with self._lock:
            if include_retired:
                return list(self._patterns.values())
            return [p for p in self._patterns.values()
                    if p.state != PatternState.RETIRED]


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: LongHorizonMemoryStore | None = None
_lock = threading.Lock()


def get_long_horizon_memory() -> LongHorizonMemoryStore:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = LongHorizonMemoryStore()
    return _instance


__all__ = [
    "HorizonWindow",
    "LongHorizonMemoryStore",
    "LongHorizonPattern",
    "LongHorizonSnapshot",
    "PatternKind",
    "PatternObservation",
    "PatternState",
    "get_long_horizon_memory",
]

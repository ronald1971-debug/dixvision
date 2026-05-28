"""Divergence Detector — pinpoints replay failures (CONVERGENCE PILLAR 4).

When replay diverges from the recording, this module identifies:
- The exact event that caused divergence
- Which field diverged
- What the expected vs actual values are
- Possible causes (non-deterministic input, missing stub, clock drift)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, auto

from runtime.replay.session_replayer import Divergence, ReplayResult


class DivergenceCause(StrEnum):
    """Possible causes of replay divergence."""

    CLOCK_DRIFT = auto()
    MISSING_IO_STUB = auto()
    NON_DETERMINISTIC_INPUT = auto()
    STATE_MUTATION_ORDER = auto()
    POLICY_VERSION_MISMATCH = auto()
    UNKNOWN = auto()


@dataclass(frozen=True, slots=True)
class DivergenceReport:
    """Detailed report of a single divergence."""

    divergence: Divergence
    probable_cause: DivergenceCause
    explanation: str
    remediation: str


@dataclass(frozen=True, slots=True)
class DivergenceAnalysis:
    """Full analysis of all divergences in a replay."""

    total_divergences: int
    first_divergence_at: int  # event sequence number
    reports: tuple[DivergenceReport, ...]
    determinism_score: float  # 0.0 = fully divergent, 1.0 = identical


def analyze_divergences(result: ReplayResult) -> DivergenceAnalysis:
    """Analyze replay divergences and produce actionable reports.

    Examines each divergence to determine the probable cause and
    suggest remediation steps.
    """
    if not result.divergences:
        return DivergenceAnalysis(
            total_divergences=0,
            first_divergence_at=-1,
            reports=(),
            determinism_score=1.0,
        )

    reports: list[DivergenceReport] = []

    for div in result.divergences:
        cause, explanation, remediation = _classify_divergence(div)
        reports.append(
            DivergenceReport(
                divergence=div,
                probable_cause=cause,
                explanation=explanation,
                remediation=remediation,
            )
        )

    # Score: fraction of events that were checkpoint-verified successfully
    if result.events_replayed > 0:
        score = 1.0 - (len(result.divergences) / result.events_replayed)
    else:
        score = 0.0

    return DivergenceAnalysis(
        total_divergences=len(result.divergences),
        first_divergence_at=result.divergences[0].event_sequence,
        reports=tuple(reports),
        determinism_score=max(0.0, score),
    )


def _classify_divergence(
    div: Divergence,
) -> tuple[DivergenceCause, str, str]:
    """Classify a divergence by its probable cause."""
    field = div.field

    if field in ("health_score",):
        return (
            DivergenceCause.STATE_MUTATION_ORDER,
            f"Health score diverged: expected {div.expected}, got {div.actual}. "
            "Likely caused by hazard events arriving in different order during replay.",
            "Ensure hazard events are replayed in exact sequence order.",
        )

    if field in ("last_market_ts_ns", "last_tick_ts_ns"):
        return (
            DivergenceCause.CLOCK_DRIFT,
            f"Timestamp field '{field}' diverged. "
            "Clock source may not be fully stubbed during replay.",
            "Verify LedgerClock injection covers all TimeAuthority call sites.",
        )

    if field in ("open_positions", "total_exposure_usd"):
        return (
            DivergenceCause.MISSING_IO_STUB,
            f"Position/exposure field '{field}' diverged. "
            "Fill events may depend on un-stubbed adapter IO.",
            "Ensure all adapter responses are recorded and stubbed during replay.",
        )

    if field == "system_mode":
        return (
            DivergenceCause.POLICY_VERSION_MISMATCH,
            "System mode diverged. Governance policy may have changed between "
            "recording and replay.",
            "Check that replay uses the same policy version as the recording.",
        )

    return (
        DivergenceCause.UNKNOWN,
        f"Field '{field}' diverged: expected {div.expected}, got {div.actual}.",
        "Manual investigation required. Check event ordering and state dependencies.",
    )

"""Credibility filter (BUILD-DIRECTIVE §15 — TIS module 3).

Filters trader profiles by credibility score before they enter the
extraction pipeline. Uses track record, consistency, and verification
signals to assign an initial credibility score.

INV-15: Pure function, no IO on hot path.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CredibilityTier(StrEnum):
    """Credibility classification tiers."""

    LEGENDARY = "LEGENDARY"  # Proven track record, published results
    VERIFIED = "VERIFIED"  # Audited returns or on-chain proof
    CLAIMED = "CLAIMED"  # Self-reported, not verified
    UNVERIFIED = "UNVERIFIED"  # New discovery, no evidence yet
    REJECTED = "REJECTED"  # Failed verification or known fraud


@dataclass(frozen=True, slots=True)
class CredibilityAssessment:
    """Result of credibility filtering."""

    trader_id: str
    tier: CredibilityTier
    score: float  # 0.0 = no credibility, 1.0 = maximum
    evidence_count: int
    verification_sources: tuple[str, ...]
    decay_factor: float  # how much to discount older data
    pass_filter: bool  # whether to proceed to extraction


class CredibilityFilter:
    """Filters traders by credibility before extraction.

    Traders must meet minimum credibility to enter the pipeline.
    This prevents garbage-in from poisoning strategy atoms.
    """

    def __init__(
        self,
        *,
        min_score: float = 0.3,
        min_evidence: int = 1,
    ) -> None:
        self._min_score = min_score
        self._min_evidence = min_evidence

    def assess(
        self,
        *,
        trader_id: str,
        track_record_years: float = 0.0,
        verified_returns: bool = False,
        onchain_proof: bool = False,
        published_results: bool = False,
        peer_citations: int = 0,
        known_fraud: bool = False,
        self_reported_only: bool = True,
    ) -> CredibilityAssessment:
        """Assess a trader's credibility for the pipeline."""
        if known_fraud:
            return CredibilityAssessment(
                trader_id=trader_id,
                tier=CredibilityTier.REJECTED,
                score=0.0,
                evidence_count=0,
                verification_sources=(),
                decay_factor=0.0,
                pass_filter=False,
            )

        evidence: list[str] = []
        score = 0.0

        if track_record_years >= 10.0:
            score += 0.3
            evidence.append("long_track_record")
        elif track_record_years >= 3.0:
            score += 0.15
            evidence.append("medium_track_record")

        if verified_returns:
            score += 0.3
            evidence.append("verified_returns")

        if onchain_proof:
            score += 0.2
            evidence.append("onchain_proof")

        if published_results:
            score += 0.15
            evidence.append("published_results")

        if peer_citations >= 10:
            score += 0.1
            evidence.append("highly_cited")
        elif peer_citations >= 3:
            score += 0.05
            evidence.append("cited")

        # Cap at 1.0
        score = min(score, 1.0)

        # Determine tier
        if score >= 0.7:
            tier = CredibilityTier.LEGENDARY
        elif score >= 0.4:
            tier = CredibilityTier.VERIFIED
        elif not self_reported_only:
            tier = CredibilityTier.CLAIMED
        else:
            tier = CredibilityTier.UNVERIFIED

        # Decay: older data is less reliable
        decay = 1.0 / (1.0 + max(0.0, track_record_years - 20.0) * 0.05)

        pass_filter = score >= self._min_score and len(evidence) >= self._min_evidence

        return CredibilityAssessment(
            trader_id=trader_id,
            tier=tier,
            score=score,
            evidence_count=len(evidence),
            verification_sources=tuple(evidence),
            decay_factor=decay,
            pass_filter=pass_filter,
        )

"""Trader profile engine (BUILD-DIRECTIVE §15 — TIS module 7).

Maintains and evolves complete trader profiles over time. A profile
is the comprehensive model of a trader: identity, philosophy, strategy
atoms, performance history, credibility, and current activity state.

All profiles are ledgered (EVENT: TRADER_PROFILE_PROMOTED).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ProfileStatus(StrEnum):
    """Current status of a trader profile."""

    ACTIVE = "ACTIVE"  # Actively tracked, atoms used in composition
    INACTIVE = "INACTIVE"  # Historical only, not used in composition
    SUSPENDED = "SUSPENDED"  # Under review (credibility issue)
    ARCHIVED = "ARCHIVED"  # Permanently archived


@dataclass(slots=True)
class TraderProfile:
    """Complete model of a tracked trader."""

    canonical_id: str
    display_name: str
    status: ProfileStatus
    credibility_score: float
    philosophy_vector: tuple[float, ...] = ()
    archetype: str = ""  # macro, quant, discretionary, crypto_native, hft
    timeframe_bias: str = ""  # scalper, day, swing, position, investor
    atom_ids: list[str] = field(default_factory=list)
    total_observations: int = 0
    last_observation_ts_ns: int = 0
    performance_metrics: dict[str, float] = field(default_factory=dict)
    era: str = ""  # historical, modern, current
    domains: list[str] = field(default_factory=list)


class TraderProfileEngine:
    """Manages the lifecycle of trader profiles.

    Responsibilities:
    - Create profiles from resolved identities
    - Update profiles with new observations
    - Track performance metrics over time
    - Manage profile status transitions
    - Provide profile lookup for composition
    """

    def __init__(self) -> None:
        self._profiles: dict[str, TraderProfile] = {}

    def create_profile(
        self,
        *,
        canonical_id: str,
        display_name: str,
        archetype: str = "",
        timeframe_bias: str = "",
        credibility_score: float = 0.5,
        era: str = "current",
        domains: list[str] | None = None,
    ) -> TraderProfile:
        """Create a new trader profile."""
        profile = TraderProfile(
            canonical_id=canonical_id,
            display_name=display_name,
            status=ProfileStatus.ACTIVE,
            credibility_score=credibility_score,
            archetype=archetype,
            timeframe_bias=timeframe_bias,
            era=era,
            domains=domains or [],
        )
        self._profiles[canonical_id] = profile
        return profile

    def update_observation(
        self,
        *,
        canonical_id: str,
        atom_ids: list[str] | None = None,
        performance: dict[str, float] | None = None,
        ts_ns: int = 0,
    ) -> TraderProfile | None:
        """Update a profile with new observation data."""
        profile = self._profiles.get(canonical_id)
        if profile is None:
            return None

        if atom_ids:
            profile.atom_ids.extend(atom_ids)
        if performance:
            profile.performance_metrics.update(performance)
        profile.total_observations += 1
        if ts_ns > 0:
            profile.last_observation_ts_ns = ts_ns
        return profile

    def get_active_profiles(self, *, archetype: str | None = None) -> list[TraderProfile]:
        """Get all active profiles, optionally filtered by archetype."""
        results = []
        for p in self._profiles.values():
            if p.status != ProfileStatus.ACTIVE:
                continue
            if archetype and p.archetype != archetype:
                continue
            results.append(p)
        return results

    def get_profile(self, canonical_id: str) -> TraderProfile | None:
        """Lookup a profile by canonical ID."""
        return self._profiles.get(canonical_id)

    def suspend_profile(self, canonical_id: str) -> bool:
        """Suspend a profile (credibility issue)."""
        profile = self._profiles.get(canonical_id)
        if profile is None:
            return False
        profile.status = ProfileStatus.SUSPENDED
        return True

    def get_top_by_metric(
        self, metric: str, *, n: int = 10, min_observations: int = 5
    ) -> list[TraderProfile]:
        """Get top N profiles ranked by a performance metric."""
        candidates = [
            p
            for p in self._profiles.values()
            if p.status == ProfileStatus.ACTIVE
            and p.total_observations >= min_observations
            and metric in p.performance_metrics
        ]
        candidates.sort(key=lambda p: p.performance_metrics.get(metric, 0.0), reverse=True)
        return candidates[:n]

    @property
    def profile_count(self) -> int:
        """Total profiles managed."""
        return len(self._profiles)

    def to_registry_snapshot(self) -> list[dict[str, Any]]:
        """Export all profiles as a serializable snapshot."""
        return [
            {
                "canonical_id": p.canonical_id,
                "display_name": p.display_name,
                "status": p.status.value,
                "credibility_score": p.credibility_score,
                "archetype": p.archetype,
                "atom_count": len(p.atom_ids),
                "observations": p.total_observations,
            }
            for p in self._profiles.values()
        ]

"""Trader profile store (state.memory_tensor.trader_patterns.profile_store).

TI persistence layer — stores immutable :class:`TraderProfile` records in
an in-memory dict with upsert semantics keyed by ``profile_id``.

Authority constraints:
* B1: No imports from intelligence_engine, execution_engine, governance_engine,
  evolution_engine, learning_engine.
* B27/B28/INV-71: Never constructs SignalEvent, ExecutionEvent, HazardEvent,
  PatchProposal.
* INV-15: Pure functions — no wall-clock reads.
* RUNTIME_SAFE: no clocks, no IO, no PRNG in core value objects.
* Frozen dataclasses: (frozen=True, slots=True).
"""

from __future__ import annotations

import dataclasses
import threading


__all__ = (
    "TraderProfile",
    "TraderProfileStore",
)


# ---------------------------------------------------------------------------
# Value object
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class TraderProfile:
    """Immutable snapshot of a trader's behavioural profile.

    Fields
    ------
    profile_id:
        Unique identifier for this trader profile.
    ts_ns:
        Observation timestamp in nanoseconds (caller-supplied).
    source:
        Symbolic name of the system that generated this profile
        (e.g. ``"TI_CLASSIFIER_V2"``).
    behavior_tags:
        Ordered tuple of behavioural classification tags
        (e.g. ``("momentum", "high_frequency")``).
    performance_score:
        Scalar summary metric for this trader's recent performance.
        Defaults to ``0.0``.
    """

    profile_id: str
    ts_ns: int
    source: str
    behavior_tags: tuple[str, ...]
    performance_score: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.profile_id, str) or not self.profile_id:
            raise ValueError(
                f"TraderProfile.profile_id must be non-empty str, got {self.profile_id!r}"
            )
        if not isinstance(self.ts_ns, int) or isinstance(self.ts_ns, bool):
            raise ValueError(
                f"TraderProfile.ts_ns must be int, got {type(self.ts_ns).__name__}"
            )
        if not isinstance(self.source, str) or not self.source:
            raise ValueError(
                f"TraderProfile.source must be non-empty str, got {self.source!r}"
            )
        if not isinstance(self.behavior_tags, tuple):
            raise ValueError(
                "TraderProfile.behavior_tags must be tuple, "
                f"got {type(self.behavior_tags).__name__}"
            )
        for i, tag in enumerate(self.behavior_tags):
            if not isinstance(tag, str):
                raise ValueError(
                    f"TraderProfile.behavior_tags[{i}] must be str, got {type(tag).__name__}"
                )
        if not isinstance(self.performance_score, float):
            raise ValueError(
                "TraderProfile.performance_score must be float, "
                f"got {type(self.performance_score).__name__}"
            )


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class TraderProfileStore:
    """Thread-safe in-memory store for :class:`TraderProfile` objects.

    Upsert semantics: the latest profile for each ``profile_id`` wins.
    """

    __slots__ = ("_lock", "_profiles")

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._profiles: dict[str, TraderProfile] = {}

    def upsert(self, profile: TraderProfile) -> None:
        """Insert or replace the profile for ``profile.profile_id``.

        Raises
        ------
        TypeError:
            If *profile* is not a :class:`TraderProfile`.
        """
        if not isinstance(profile, TraderProfile):
            raise TypeError(
                f"TraderProfileStore.upsert: expected TraderProfile, "
                f"got {type(profile).__name__}"
            )
        with self._lock:
            self._profiles[profile.profile_id] = profile

    def get(self, profile_id: str) -> TraderProfile | None:
        """Return the :class:`TraderProfile` for *profile_id*, or ``None``."""
        if not isinstance(profile_id, str) or not profile_id:
            raise ValueError(
                "TraderProfileStore.get: profile_id must be non-empty str"
            )
        with self._lock:
            return self._profiles.get(profile_id)

    def all_profiles(self) -> tuple[TraderProfile, ...]:
        """Return all profiles.

        Sorted by ``performance_score`` descending; ties broken by
        ``profile_id`` ascending for INV-15 deterministic ordering.
        """
        with self._lock:
            profiles = list(self._profiles.values())
        profiles.sort(key=lambda p: (-p.performance_score, p.profile_id))
        return tuple(profiles)

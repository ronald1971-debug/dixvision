"""Archetype store (state.memory_tensor.trader_patterns.archetype_store).

Stores immutable :class:`Archetype` records representing trader strategy
archetypes with lifecycle states and decay characteristics.

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
    "Archetype",
    "ArchetypeStore",
)

# Allowed lifecycle state values.
_VALID_STATES: frozenset[str] = frozenset({"ACTIVE", "RETIRED", "DEGRADED"})


# ---------------------------------------------------------------------------
# Value object
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class Archetype:
    """Immutable description of one trader strategy archetype.

    Fields
    ------
    archetype_id:
        Unique identifier for this archetype.
    ts_ns:
        Creation / observation timestamp in nanoseconds (caller-supplied).
    name:
        Human-readable archetype name (e.g. ``"MomentumBreakout"``).
    state:
        Lifecycle state — one of ``"ACTIVE"``, ``"RETIRED"``,
        ``"DEGRADED"``.
    decay_rate:
        Non-negative exponential decay rate per time unit applied to
        this archetype's relevance weight.
    performance_score:
        Scalar summary metric for this archetype's recent performance.
    """

    archetype_id: str
    ts_ns: int
    name: str
    state: str
    decay_rate: float
    performance_score: float

    def __post_init__(self) -> None:
        if not isinstance(self.archetype_id, str) or not self.archetype_id:
            raise ValueError(
                f"Archetype.archetype_id must be non-empty str, got {self.archetype_id!r}"
            )
        if not isinstance(self.ts_ns, int) or isinstance(self.ts_ns, bool):
            raise ValueError(
                f"Archetype.ts_ns must be int, got {type(self.ts_ns).__name__}"
            )
        if not isinstance(self.name, str) or not self.name:
            raise ValueError(
                f"Archetype.name must be non-empty str, got {self.name!r}"
            )
        if self.state not in _VALID_STATES:
            raise ValueError(
                f"Archetype.state must be one of {sorted(_VALID_STATES)!r}, "
                f"got {self.state!r}"
            )
        if not isinstance(self.decay_rate, float):
            raise ValueError(
                f"Archetype.decay_rate must be float, got {type(self.decay_rate).__name__}"
            )
        if self.decay_rate < 0.0:
            raise ValueError(
                f"Archetype.decay_rate must be >= 0.0, got {self.decay_rate!r}"
            )
        if not isinstance(self.performance_score, float):
            raise ValueError(
                "Archetype.performance_score must be float, "
                f"got {type(self.performance_score).__name__}"
            )


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class ArchetypeStore:
    """Thread-safe in-memory store for :class:`Archetype` objects.

    Upsert semantics: the latest archetype for each ``archetype_id`` wins.
    """

    __slots__ = ("_lock", "_archetypes")

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._archetypes: dict[str, Archetype] = {}

    def upsert(self, archetype: Archetype) -> None:
        """Insert or replace the archetype for ``archetype.archetype_id``.

        Raises
        ------
        TypeError:
            If *archetype* is not an :class:`Archetype`.
        """
        if not isinstance(archetype, Archetype):
            raise TypeError(
                f"ArchetypeStore.upsert: expected Archetype, got {type(archetype).__name__}"
            )
        with self._lock:
            self._archetypes[archetype.archetype_id] = archetype

    def get(self, archetype_id: str) -> Archetype | None:
        """Return the :class:`Archetype` for *archetype_id*, or ``None``."""
        if not isinstance(archetype_id, str) or not archetype_id:
            raise ValueError(
                "ArchetypeStore.get: archetype_id must be non-empty str"
            )
        with self._lock:
            return self._archetypes.get(archetype_id)

    def active(self) -> tuple[Archetype, ...]:
        """Return all archetypes in state ``"ACTIVE"``.

        Sorted by ``performance_score`` descending; ties broken by
        ``archetype_id`` ascending for INV-15 deterministic ordering.
        """
        with self._lock:
            archetypes = [
                a for a in self._archetypes.values() if a.state == "ACTIVE"
            ]
        archetypes.sort(key=lambda a: (-a.performance_score, a.archetype_id))
        return tuple(archetypes)

    def all_archetypes(self) -> tuple[Archetype, ...]:
        """Return all archetypes regardless of state.

        Sorted by ``performance_score`` descending; ties broken by
        ``archetype_id`` ascending for INV-15 deterministic ordering.
        """
        with self._lock:
            archetypes = list(self._archetypes.values())
        archetypes.sort(key=lambda a: (-a.performance_score, a.archetype_id))
        return tuple(archetypes)

"""Strategy atom store (state.memory_tensor.trader_patterns.atom_store).

Stores immutable :class:`StrategyAtom` records — the elemental building
blocks of trader strategies — keyed by ``atom_id`` with per-profile
lookup support.

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
    "StrategyAtom",
    "StrategyAtomStore",
)


# ---------------------------------------------------------------------------
# Value object
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class StrategyAtom:
    """Immutable description of one strategy atom.

    Fields
    ------
    atom_id:
        Unique identifier for this atom.
    ts_ns:
        Creation / observation timestamp in nanoseconds (caller-supplied).
    profile_id:
        The :class:`~state.memory_tensor.trader_patterns.profile_store.TraderProfile`
        that owns this atom.
    kind:
        Categorical label for the atom type
        (e.g. ``"ENTRY_SIGNAL"``, ``"EXIT_RULE"``, ``"SIZING_FACTOR"``).
    params:
        Ordered ``(name: str, value: object)`` parameter pairs that
        parameterise this atom instance.
    """

    atom_id: str
    ts_ns: int
    profile_id: str
    kind: str
    params: tuple[tuple[str, object], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.atom_id, str) or not self.atom_id:
            raise ValueError(
                f"StrategyAtom.atom_id must be non-empty str, got {self.atom_id!r}"
            )
        if not isinstance(self.ts_ns, int) or isinstance(self.ts_ns, bool):
            raise ValueError(
                f"StrategyAtom.ts_ns must be int, got {type(self.ts_ns).__name__}"
            )
        if not isinstance(self.profile_id, str) or not self.profile_id:
            raise ValueError(
                f"StrategyAtom.profile_id must be non-empty str, got {self.profile_id!r}"
            )
        if not isinstance(self.kind, str) or not self.kind:
            raise ValueError(
                f"StrategyAtom.kind must be non-empty str, got {self.kind!r}"
            )
        if not isinstance(self.params, tuple):
            raise ValueError(
                f"StrategyAtom.params must be tuple, got {type(self.params).__name__}"
            )
        for i, pair in enumerate(self.params):
            if (
                not isinstance(pair, tuple)
                or len(pair) != 2
                or not isinstance(pair[0], str)
            ):
                raise ValueError(
                    f"StrategyAtom.params[{i}] must be (str, object) tuple, got {pair!r}"
                )


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class StrategyAtomStore:
    """Thread-safe in-memory store for :class:`StrategyAtom` objects.

    Each ``atom_id`` maps to exactly one atom.  Calling :meth:`save` with
    an existing ``atom_id`` raises :class:`ValueError` — atoms are
    immutable records; to update, the caller must use a new ``atom_id``.
    """

    __slots__ = ("_lock", "_atoms", "_by_profile")

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._atoms: dict[str, StrategyAtom] = {}
        # profile_id -> list[atom_id] for efficient per-profile lookup
        self._by_profile: dict[str, list[str]] = {}

    def save(self, atom: StrategyAtom) -> None:
        """Persist *atom*.

        Raises
        ------
        TypeError:
            If *atom* is not a :class:`StrategyAtom`.
        ValueError:
            If ``atom.atom_id`` is already stored.
        """
        if not isinstance(atom, StrategyAtom):
            raise TypeError(
                f"StrategyAtomStore.save: expected StrategyAtom, got {type(atom).__name__}"
            )
        with self._lock:
            if atom.atom_id in self._atoms:
                raise ValueError(
                    f"StrategyAtomStore.save: atom_id already present: {atom.atom_id!r}"
                )
            self._atoms[atom.atom_id] = atom
            bucket = self._by_profile.setdefault(atom.profile_id, [])
            bucket.append(atom.atom_id)

    def get(self, atom_id: str) -> StrategyAtom | None:
        """Return the :class:`StrategyAtom` for *atom_id*, or ``None``."""
        if not isinstance(atom_id, str) or not atom_id:
            raise ValueError("StrategyAtomStore.get: atom_id must be non-empty str")
        with self._lock:
            return self._atoms.get(atom_id)

    def by_profile(self, profile_id: str) -> tuple[StrategyAtom, ...]:
        """Return all atoms belonging to *profile_id*.

        Sorted by ``ts_ns`` descending (newest first); ties broken by
        ``atom_id`` ascending for INV-15 deterministic ordering.
        """
        if not isinstance(profile_id, str) or not profile_id:
            raise ValueError(
                "StrategyAtomStore.by_profile: profile_id must be non-empty str"
            )
        with self._lock:
            atom_ids = list(self._by_profile.get(profile_id, []))
            atoms = [self._atoms[aid] for aid in atom_ids if aid in self._atoms]
        atoms.sort(key=lambda a: (-a.ts_ns, a.atom_id))
        return tuple(atoms)

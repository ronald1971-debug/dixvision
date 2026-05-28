"""Market snapshot versioning (state.data_versioning.market_snapshots).

Authority constraints:
* B1: No imports from intelligence_engine, execution_engine, governance_engine,
  evolution_engine, learning_engine.
* B27/B28/INV-71: Never constructs SignalEvent, ExecutionEvent, HazardEvent,
  PatchProposal.
* INV-15: Pure functions — no wall-clock reads.
* RUNTIME_SAFE: no clocks, no IO, no PRNG.
* Frozen dataclasses: (frozen=True, slots=True).
"""

from __future__ import annotations

import dataclasses
import threading


__all__ = (
    "SnapshotVersion",
    "MarketSnapshot",
    "MarketSnapshotStore",
)


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class SnapshotVersion:
    """Immutable identifier for one market snapshot.

    Fields
    ------
    snapshot_id:
        Unique string key for this snapshot.
    ts_ns:
        Timestamp in nanoseconds (caller-supplied — no wall-clock reads).
    symbol:
        Instrument symbol this snapshot covers.
    schema_version:
        Schema version tag, defaults to ``"v1"``.
    """

    snapshot_id: str
    ts_ns: int
    symbol: str
    schema_version: str = "v1"

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot_id, str) or not self.snapshot_id:
            raise ValueError(
                f"SnapshotVersion.snapshot_id must be non-empty str, got {self.snapshot_id!r}"
            )
        if not isinstance(self.ts_ns, int) or isinstance(self.ts_ns, bool):
            raise ValueError(
                f"SnapshotVersion.ts_ns must be int, got {type(self.ts_ns).__name__}"
            )
        if not isinstance(self.symbol, str) or not self.symbol:
            raise ValueError(
                f"SnapshotVersion.symbol must be non-empty str, got {self.symbol!r}"
            )
        if not isinstance(self.schema_version, str) or not self.schema_version:
            raise ValueError(
                "SnapshotVersion.schema_version must be non-empty str, "
                f"got {self.schema_version!r}"
            )


@dataclasses.dataclass(frozen=True, slots=True)
class MarketSnapshot:
    """One versioned market snapshot.

    Fields
    ------
    version:
        The :class:`SnapshotVersion` identity object.
    fields:
        Ordered key-value pairs representing the snapshot payload.
        Each element is a ``(key: str, value: object)`` pair stored as
        a tuple of 2-tuples so the dataclass remains hashable and
        frozen.
    """

    version: SnapshotVersion
    fields: tuple[tuple[str, object], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.version, SnapshotVersion):
            raise ValueError(
                "MarketSnapshot.version must be SnapshotVersion, "
                f"got {type(self.version).__name__}"
            )
        if not isinstance(self.fields, tuple):
            raise ValueError(
                f"MarketSnapshot.fields must be tuple, got {type(self.fields).__name__}"
            )
        for i, pair in enumerate(self.fields):
            if (
                not isinstance(pair, tuple)
                or len(pair) != 2
                or not isinstance(pair[0], str)
            ):
                raise ValueError(
                    f"MarketSnapshot.fields[{i}] must be (str, object) tuple, got {pair!r}"
                )


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class MarketSnapshotStore:
    """Thread-safe in-memory store for :class:`MarketSnapshot` objects.

    Keyed by ``snapshot_id``. Multiple snapshots for the same symbol are
    retained so callers can query version history.
    """

    __slots__ = ("_lock", "_store")

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._store: dict[str, MarketSnapshot] = {}

    def save(self, snapshot: MarketSnapshot) -> None:
        """Persist *snapshot*, overwriting any previous entry with the same id."""
        if not isinstance(snapshot, MarketSnapshot):
            raise TypeError(
                f"MarketSnapshotStore.save: expected MarketSnapshot, "
                f"got {type(snapshot).__name__}"
            )
        with self._lock:
            self._store[snapshot.version.snapshot_id] = snapshot

    def load(self, snapshot_id: str) -> MarketSnapshot | None:
        """Return the snapshot for *snapshot_id*, or ``None`` if absent."""
        if not isinstance(snapshot_id, str) or not snapshot_id:
            raise ValueError(
                "MarketSnapshotStore.load: snapshot_id must be non-empty str"
            )
        with self._lock:
            return self._store.get(snapshot_id)

    def list_versions(self, symbol: str) -> tuple[SnapshotVersion, ...]:
        """Return all :class:`SnapshotVersion` objects for *symbol*.

        Sorted by ``ts_ns`` descending (newest first).  Ties broken by
        ``snapshot_id`` ascending for deterministic INV-15 ordering.
        """
        if not isinstance(symbol, str) or not symbol:
            raise ValueError(
                "MarketSnapshotStore.list_versions: symbol must be non-empty str"
            )
        with self._lock:
            versions = [
                snap.version
                for snap in self._store.values()
                if snap.version.symbol == symbol
            ]
        versions.sort(key=lambda v: (-v.ts_ns, v.snapshot_id))
        return tuple(versions)

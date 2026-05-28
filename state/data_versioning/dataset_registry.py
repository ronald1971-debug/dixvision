"""Dataset registry (state.data_versioning.dataset_registry).

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
    "DatasetEntry",
    "DatasetRegistry",
)


# ---------------------------------------------------------------------------
# Value object
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class DatasetEntry:
    """Immutable registry record for one dataset version.

    Fields
    ------
    dataset_id:
        Unique identifier for the dataset (caller-supplied).
    ts_ns:
        Registration timestamp in nanoseconds (caller-supplied — no
        wall-clock reads per INV-15).
    kind:
        Categorical label describing the dataset type
        (e.g. ``"OHLCV"``, ``"FEATURES"``, ``"TRADES"``).
    row_count:
        Number of rows in the dataset at registration time.
    digest:
        Content digest string (e.g. SHA-256 hex, or any stable hash)
        that the caller computes over the dataset payload.
    """

    dataset_id: str
    ts_ns: int
    kind: str
    row_count: int
    digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.dataset_id, str) or not self.dataset_id:
            raise ValueError(
                f"DatasetEntry.dataset_id must be non-empty str, got {self.dataset_id!r}"
            )
        if not isinstance(self.ts_ns, int) or isinstance(self.ts_ns, bool):
            raise ValueError(
                f"DatasetEntry.ts_ns must be int, got {type(self.ts_ns).__name__}"
            )
        if not isinstance(self.kind, str) or not self.kind:
            raise ValueError(
                f"DatasetEntry.kind must be non-empty str, got {self.kind!r}"
            )
        if not isinstance(self.row_count, int) or isinstance(self.row_count, bool):
            raise ValueError(
                f"DatasetEntry.row_count must be int, got {type(self.row_count).__name__}"
            )
        if self.row_count < 0:
            raise ValueError(
                f"DatasetEntry.row_count must be >= 0, got {self.row_count!r}"
            )
        if not isinstance(self.digest, str) or not self.digest:
            raise ValueError(
                f"DatasetEntry.digest must be non-empty str, got {self.digest!r}"
            )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class DatasetRegistry:
    """Thread-safe in-memory registry for :class:`DatasetEntry` objects.

    Each ``dataset_id`` maps to exactly one entry; calling
    :meth:`register` with an existing id overwrites the previous entry
    (last-writer-wins semantics).
    """

    __slots__ = ("_lock", "_entries")

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._entries: dict[str, DatasetEntry] = {}

    def register(self, entry: DatasetEntry) -> None:
        """Register *entry*, overwriting any previous entry with the same id.

        Raises
        ------
        TypeError:
            If *entry* is not a :class:`DatasetEntry`.
        """
        if not isinstance(entry, DatasetEntry):
            raise TypeError(
                f"DatasetRegistry.register: expected DatasetEntry, got {type(entry).__name__}"
            )
        with self._lock:
            self._entries[entry.dataset_id] = entry

    def lookup(self, dataset_id: str) -> DatasetEntry | None:
        """Return the :class:`DatasetEntry` for *dataset_id*, or ``None``."""
        if not isinstance(dataset_id, str) or not dataset_id:
            raise ValueError(
                "DatasetRegistry.lookup: dataset_id must be non-empty str"
            )
        with self._lock:
            return self._entries.get(dataset_id)

    def all_entries(self) -> tuple[DatasetEntry, ...]:
        """Return all registered entries.

        Sorted by ``ts_ns`` descending (newest first); ties broken by
        ``dataset_id`` ascending for INV-15 deterministic ordering.
        """
        with self._lock:
            entries = list(self._entries.values())
        entries.sort(key=lambda e: (-e.ts_ns, e.dataset_id))
        return tuple(entries)

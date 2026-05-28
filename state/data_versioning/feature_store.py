"""Feature versioning store (state.data_versioning.feature_store).

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
import hashlib
import json
import threading


__all__ = (
    "FeatureVersion",
    "FeatureRecord",
    "FeatureStore",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_checksum(values: tuple[tuple[str, float], ...]) -> str:
    """Return BLAKE2b-128 hex digest of canonical JSON of *values*.

    Canonical form: ``json.dumps`` over a sorted list of ``[key, value]``
    pairs with ``separators=(",", ":")`` and ``sort_keys=True``.
    The sort guarantees INV-15 byte-identical output regardless of the
    insertion order passed by the caller.
    """
    canonical = json.dumps(
        sorted(([k, v] for k, v in values), key=lambda kv: kv[0]),
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.blake2b(canonical.encode("utf-8"), digest_size=16).hexdigest()


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class FeatureVersion:
    """Immutable identity for one feature snapshot.

    Fields
    ------
    feature_id:
        Caller-supplied unique identifier for this feature set.
    ts_ns:
        Timestamp in nanoseconds (caller-supplied — no wall-clock reads).
    source:
        Symbolic name of the upstream that produced these features.
    checksum:
        BLAKE2b-128 hex digest of the canonical JSON of the
        corresponding :class:`FeatureRecord` ``values``.  Computed
        automatically by :class:`FeatureStore` — callers should pass
        the value returned from :func:`_compute_checksum`.
    """

    feature_id: str
    ts_ns: int
    source: str
    checksum: str

    def __post_init__(self) -> None:
        if not isinstance(self.feature_id, str) or not self.feature_id:
            raise ValueError(
                f"FeatureVersion.feature_id must be non-empty str, got {self.feature_id!r}"
            )
        if not isinstance(self.ts_ns, int) or isinstance(self.ts_ns, bool):
            raise ValueError(
                f"FeatureVersion.ts_ns must be int, got {type(self.ts_ns).__name__}"
            )
        if not isinstance(self.source, str) or not self.source:
            raise ValueError(
                f"FeatureVersion.source must be non-empty str, got {self.source!r}"
            )
        if not isinstance(self.checksum, str) or not self.checksum:
            raise ValueError(
                f"FeatureVersion.checksum must be non-empty str, got {self.checksum!r}"
            )


@dataclasses.dataclass(frozen=True, slots=True)
class FeatureRecord:
    """One versioned feature snapshot.

    Fields
    ------
    version:
        The :class:`FeatureVersion` identity object.
    values:
        Ordered ``(feature_name: str, value: float)`` pairs.
    """

    version: FeatureVersion
    values: tuple[tuple[str, float], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.version, FeatureVersion):
            raise ValueError(
                "FeatureRecord.version must be FeatureVersion, "
                f"got {type(self.version).__name__}"
            )
        if not isinstance(self.values, tuple):
            raise ValueError(
                f"FeatureRecord.values must be tuple, got {type(self.values).__name__}"
            )
        for i, pair in enumerate(self.values):
            if (
                not isinstance(pair, tuple)
                or len(pair) != 2
                or not isinstance(pair[0], str)
                or not isinstance(pair[1], float)
            ):
                raise ValueError(
                    f"FeatureRecord.values[{i}] must be (str, float) tuple, got {pair!r}"
                )


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class FeatureStore:
    """Thread-safe in-memory store for :class:`FeatureRecord` objects.

    Multiple records with the same ``feature_id`` are retained so callers
    can query the full version history.  The checksum is verified on store
    to catch caller bugs early.

    Usage::

        store = FeatureStore()
        values = (("rsi_14", 0.62), ("adx_14", 0.34))
        checksum = FeatureStore.compute_checksum(values)
        version = FeatureVersion(
            feature_id="feat.AAPL.1",
            ts_ns=1_700_000_000_000_000_000,
            source="feature_pipeline_v3",
            checksum=checksum,
        )
        record = FeatureRecord(version=version, values=values)
        store.store(record)
    """

    __slots__ = ("_lock", "_by_id")

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        # Maps feature_id -> list of records (may have multiple versions)
        self._by_id: dict[str, list[FeatureRecord]] = {}

    # ------------------------------------------------------------------
    # Class-level helper — exposed so callers can compute the checksum
    # before constructing a FeatureVersion.
    # ------------------------------------------------------------------

    @staticmethod
    def compute_checksum(values: tuple[tuple[str, float], ...]) -> str:
        """Return BLAKE2b-128 hex digest of canonical JSON of *values*."""
        return _compute_checksum(values)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def store(self, record: FeatureRecord) -> None:
        """Persist *record*.

        Validates that the checksum encoded in ``record.version.checksum``
        matches a freshly computed digest of ``record.values``.

        Raises
        ------
        TypeError:
            If *record* is not a :class:`FeatureRecord`.
        ValueError:
            If the embedded checksum does not match the computed digest.
        """
        if not isinstance(record, FeatureRecord):
            raise TypeError(
                f"FeatureStore.store: expected FeatureRecord, got {type(record).__name__}"
            )
        expected = _compute_checksum(record.values)
        if record.version.checksum != expected:
            raise ValueError(
                f"FeatureStore.store: checksum mismatch for feature_id="
                f"{record.version.feature_id!r}; "
                f"embedded={record.version.checksum!r}, computed={expected!r}"
            )
        with self._lock:
            bucket = self._by_id.setdefault(record.version.feature_id, [])
            bucket.append(record)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def fetch(self, feature_id: str) -> FeatureRecord | None:
        """Return the most-recent :class:`FeatureRecord` for *feature_id*.

        "Most recent" means highest ``ts_ns``; ties broken by
        ``feature_id`` (string order) for INV-15 determinism.

        Returns ``None`` if no record exists for *feature_id*.
        """
        if not isinstance(feature_id, str) or not feature_id:
            raise ValueError("FeatureStore.fetch: feature_id must be non-empty str")
        with self._lock:
            bucket = self._by_id.get(feature_id)
            if not bucket:
                return None
            return max(bucket, key=lambda r: (r.version.ts_ns, r.version.feature_id))

    def versions(self, feature_id: str) -> tuple[FeatureVersion, ...]:
        """Return all :class:`FeatureVersion` objects for *feature_id*.

        Sorted by ``ts_ns`` descending (newest first); ties broken by
        ``feature_id`` ascending for INV-15 deterministic ordering.
        """
        if not isinstance(feature_id, str) or not feature_id:
            raise ValueError("FeatureStore.versions: feature_id must be non-empty str")
        with self._lock:
            bucket = self._by_id.get(feature_id, [])
            vers = [r.version for r in bucket]
        vers.sort(key=lambda v: (-v.ts_ns, v.feature_id))
        return tuple(vers)

"""core/contracts/ledger.py
DIX VISION v42.2 — Ledger subsystem contract types.

Read-only value objects that cross the boundary between ledger writers
and all consumers (coherence, governance, reporting). Like all
core.contracts they are frozen, slotted, replay-deterministic value
objects (INV-08, INV-15). No callables, no IO.

The ledger records five first-class stream kinds (MARKET, SYSTEM,
GOVERNANCE, HAZARD, AUTHORITY) plus a HAZARD_RESOLVED transition so
consumers can reconstruct open-hazard windows without a full replay.

LedgerEntry is the canonical serialisation unit: each row carries a
cryptographic chain via ``prev_hash`` → ``event_hash`` so the
LedgerHealthReport can report ``chain_valid`` without a full scan.

Refs:
- INV-08 (typed events across domain boundaries)
- INV-15 (replay determinism — frozen, no callables)
- INV-53 (calibration hook requires ledger replay of SYSTEM rows)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LedgerStreamKind(StrEnum):
    """Discriminator for the six canonical ledger stream kinds."""

    MARKET = "MARKET"
    SYSTEM = "SYSTEM"
    GOVERNANCE = "GOVERNANCE"
    HAZARD = "HAZARD"
    HAZARD_RESOLVED = "HAZARD_RESOLVED"
    AUTHORITY = "AUTHORITY"


@dataclass(frozen=True, slots=True)
class LedgerQueryFilter:
    """Immutable query specification for ledger reads.

    All fields are optional (``None`` = no constraint). Callers build
    a filter and pass it to a reader; the filter is never mutated.

    Fields:
        stream_kind: Restrict to a single :class:`LedgerStreamKind`.
        source: Restrict to a specific producer (engine name / module
            path, e.g. ``"core.coherence.belief_state"``).
        sub_type: Restrict to a specific sub-kind string (mirrors
            :attr:`~core.contracts.events.SystemEventKind` values when
            used on the SYSTEM stream).
        limit: Maximum number of rows to return. ``None`` = unlimited.
        since_ts_ns: Return only rows with ``ts_ns >= since_ts_ns``.
            ``None`` = no lower bound.
    """

    stream_kind: LedgerStreamKind | None = None
    source: str | None = None
    sub_type: str | None = None
    limit: int | None = None
    since_ts_ns: int | None = None


@dataclass(frozen=True, slots=True)
class LedgerHealthReport:
    """Snapshot result of a ledger integrity self-check.

    Produced by ``LedgerAuthorityWriter.health_check()`` and surfaced
    to governance via the SYSTEM ledger stream (sub_kind HEALTH_REPORT).

    Fields:
        ts_ns: Timestamp at which the check was performed (nanoseconds).
        chain_valid: True if the hash chain from genesis to the latest
            row is unbroken (no gaps, no tampered hashes).
        event_count: Total number of rows across all streams.
        last_hash: ``event_hash`` of the most-recently appended row,
            or the empty string if the ledger is empty.
        storage_bytes: Approximate on-disk size of all ledger files.
            ``-1`` if unavailable (e.g. in-memory ledger).
        detail: Human-readable summary / error description.
    """

    ts_ns: int
    chain_valid: bool
    event_count: int
    last_hash: str
    storage_bytes: int
    detail: str = ""


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """Canonical serialisation unit for every ledger row (INV-08).

    Each engine writes typed events; the ledger wraps them in this
    envelope so that any downstream reader can reconstruct the full
    event without knowing the specific event type in advance.

    Hash chain (INV-15):
        ``event_hash = sha256(prev_hash | stream_kind | sub_type |
        source | sequence | ts_ns | canonical_payload)``

    The hash function is deterministic — same inputs always produce the
    same bytes. ``prev_hash`` is the ``event_hash`` of the previous row
    in the *same stream* (or the empty string for the genesis row).

    Fields:
        event_id: Globally unique identifier (UUIDv4 or stable hash).
        stream_kind: Which ledger stream this row belongs to.
        sub_type: Fine-grained event sub-type (e.g. a
            :class:`~core.contracts.events.SystemEventKind` value).
        source: Producing engine / module path.
        payload: Serialised event data. Keys and values are both
            strings; the schema is governed by ``sub_type``.
        ts_ns: Nanosecond timestamp (TimeAuthority, T0-04).
        sequence: Monotonically increasing row index within the
            stream. Starts at 0 for the genesis row.
        prev_hash: ``event_hash`` of the previous row in the stream
            (empty string for the genesis row).
        event_hash: Cryptographic commitment over all other fields.
    """

    event_id: str
    stream_kind: LedgerStreamKind
    sub_type: str
    source: str
    payload: dict  # type: ignore[type-arg]  # str → Any; kept loose for flexibility
    ts_ns: int
    sequence: int
    prev_hash: str
    event_hash: str


@dataclass(frozen=True, slots=True)
class ReconstructedState:
    """Result of replaying a ledger stream up to a point in time.

    Produced by offline calibrators and audit tools that fold a stream
    slice into a single summary value object. ``checksum`` is a
    deterministic hex digest of all ``event_hash`` values in the
    replayed window (sorted by ``sequence`` then XOR-folded), so two
    independent replays of the same slice always yield the same
    checksum (INV-15).

    Fields:
        ts_ns: Timestamp of the latest row included in the replay.
        stream_kind: Stream that was replayed.
        event_count: Number of rows included.
        checksum: Deterministic hex digest of the replayed window.
        detail: Human-readable description or error summary.
    """

    ts_ns: int
    stream_kind: LedgerStreamKind
    event_count: int
    checksum: str
    detail: str = ""


__all__ = [
    "LedgerEntry",
    "LedgerHealthReport",
    "LedgerQueryFilter",
    "LedgerStreamKind",
    "ReconstructedState",
]

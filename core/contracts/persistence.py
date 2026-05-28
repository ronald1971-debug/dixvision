"""
core/contracts/persistence.py
DIX VISION v42.2 — Persistence Layer Contracts

Production-grade persistence protocols and value types used across
the system for state snapshotting, event sourcing, and recovery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from system import time_source


class PersistenceBackend(StrEnum):
    """Supported persistence backends."""

    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    TIMESCALEDB = "timescaledb"
    MEMORY = "memory"


class SnapshotStatus(StrEnum):
    """Lifecycle status of a persisted snapshot."""

    PENDING = "pending"
    WRITING = "writing"
    COMMITTED = "committed"
    CORRUPTED = "corrupted"
    ARCHIVED = "archived"


@dataclass(frozen=True, slots=True)
class PersistenceConfig:
    """Configuration for a persistence backend connection."""

    backend: PersistenceBackend
    dsn: str = ""
    pool_size: int = 5
    max_overflow: int = 10
    timeout_ms: int = 5000
    retry_count: int = 3


@dataclass(frozen=True, slots=True)
class SnapshotMetadata:
    """Metadata for a persisted state snapshot."""

    snapshot_id: str
    version: int
    status: SnapshotStatus
    size_bytes: int
    checksum_sha256: str
    created_at_ns: int
    source_engine: str
    parent_snapshot_id: str = ""


@dataclass(frozen=True, slots=True)
class WriteResult:
    """Result of a persistence write operation."""

    success: bool
    snapshot_id: str
    bytes_written: int
    duration_ms: float
    ts_ns: int = field(default_factory=time_source.wall_ns)
    error: str = ""


@dataclass(frozen=True, slots=True)
class RestoreResult:
    """Result of a persistence restore operation."""

    success: bool
    snapshot_id: str
    version: int
    bytes_read: int
    duration_ms: float
    ts_ns: int = field(default_factory=time_source.wall_ns)
    error: str = ""


@runtime_checkable
class IPersistence(Protocol):
    """Protocol: persistence layer contract.

    Concrete implementations (SQLite ledger, PostgreSQL, TimescaleDB)
    must satisfy this protocol. The system uses dependency inversion
    so engines never directly instantiate a backend.
    """

    def save(self, engine_id: str, state: bytes, *, version: int = 0) -> WriteResult:
        """Persist an engine state snapshot.

        Args:
            engine_id: Source engine identifier.
            state: Serialized state bytes (msgpack or protobuf).
            version: Monotonically increasing version number.

        Returns:
            WriteResult with success status, bytes written, timing.
        """
        ...

    def restore(self, engine_id: str, *, version: int | None = None) -> RestoreResult:
        """Restore the latest (or specific version) snapshot.

        Args:
            engine_id: Engine whose state to restore.
            version: Specific version to restore (None = latest).

        Returns:
            RestoreResult with the recovered state bytes.
        """
        ...

    def list_snapshots(self, engine_id: str, *, limit: int = 50) -> list[SnapshotMetadata]:
        """List available snapshots for an engine.

        Args:
            engine_id: Engine identifier to query.
            limit: Maximum number of snapshots to return.

        Returns:
            List of SnapshotMetadata in reverse chronological order.
        """
        ...

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a specific snapshot by ID.

        Returns:
            True if deleted, False if not found.
        """
        ...

    def verify_integrity(self, snapshot_id: str) -> bool:
        """Verify checksum integrity of a persisted snapshot.

        Returns:
            True if checksum matches, False if corrupted.
        """
        ...

    @property
    def backend(self) -> PersistenceBackend:
        """The active persistence backend type."""
        ...

    @property
    def is_connected(self) -> bool:
        """Whether the backend connection is alive."""
        ...


__all__ = [
    "IPersistence",
    "PersistenceBackend",
    "PersistenceConfig",
    "RestoreResult",
    "SnapshotMetadata",
    "SnapshotStatus",
    "WriteResult",
]

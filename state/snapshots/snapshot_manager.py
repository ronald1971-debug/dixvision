"""state.snapshots.snapshot_manager — Periodic State Snapshot Engine.

Manages periodic snapshots of the runtime state for fast recovery. Writes
atomic point-in-time snapshots of all engine states, portfolio, governance
decisions, and learning progress to disk.

Snapshots are versioned, hash-verified, and replay-aligned (INV-15). A
snapshot + ledger suffix = full deterministic reconstruction.

Schema per snapshot:
  - metadata: version, ts_ns, mode, tick_count, hash
  - portfolio: positions, balances, exposure
  - governance: current mode, last transition, authority state
  - learning: progress scores, active hypotheses count
  - engines: per-engine health + config
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from system import time_source


class SnapshotStatus(StrEnum):
    """Lifecycle of a snapshot write."""

    PENDING = "PENDING"
    WRITING = "WRITING"
    COMMITTED = "COMMITTED"
    CORRUPTED = "CORRUPTED"
    ARCHIVED = "ARCHIVED"


@dataclass(frozen=True, slots=True)
class SnapshotMetadata:
    """Metadata header for a persisted snapshot."""

    snapshot_id: str
    version: int
    ts_ns: int
    mode: str
    tick_count: int
    content_hash: str
    ledger_position: int
    size_bytes: int = 0
    status: SnapshotStatus = SnapshotStatus.COMMITTED


@dataclass(frozen=True, slots=True)
class SnapshotConfig:
    """Configuration for the snapshot manager."""

    base_dir: str = "state/snapshots/data"
    interval_ticks: int = 1000
    max_snapshots: int = 100
    compress: bool = True
    verify_on_read: bool = True


class SnapshotManager:
    """Manages periodic state snapshots for fast recovery.

    Writes atomic point-in-time state to disk at configured intervals.
    Supports recovery by loading latest valid snapshot + replaying
    ledger events from that point forward (INV-15 deterministic replay).
    """

    __slots__ = ("_config", "_snapshots", "_tick_counter", "_base_path")

    def __init__(self, config: SnapshotConfig | None = None) -> None:
        self._config = config or SnapshotConfig()
        self._snapshots: list[SnapshotMetadata] = []
        self._tick_counter = 0
        self._base_path = Path(self._config.base_dir)
        self._base_path.mkdir(parents=True, exist_ok=True)

    def tick(self, state: dict[str, Any]) -> SnapshotMetadata | None:
        """Called every tick. Writes snapshot if interval reached.

        Args:
            state: Current runtime state dictionary.

        Returns:
            SnapshotMetadata if a snapshot was written, None otherwise.
        """
        self._tick_counter += 1
        if self._tick_counter % self._config.interval_ticks != 0:
            return None
        return self.write_snapshot(state)

    def write_snapshot(self, state: dict[str, Any]) -> SnapshotMetadata:
        """Write an immediate snapshot of the current state.

        Args:
            state: Runtime state to snapshot.

        Returns:
            Metadata of the written snapshot.
        """
        ts_ns = time_source.wall_ns()
        snapshot_id = f"snap_{ts_ns}"
        # Hash computed over pure state only (no metadata fields)
        state_content = json.dumps(state, default=str, sort_keys=True)
        content_hash = hashlib.blake2b(state_content.encode(), digest_size=32).hexdigest()

        # Stored document embeds hash + metadata alongside state
        stored: dict[str, Any] = {
            "_content_hash": content_hash,
            "_version": 3,
            "_ts_ns": ts_ns,
            "_tick_count": self._tick_counter,
            **state,
        }
        stored_text = json.dumps(stored, default=str, sort_keys=True)

        filepath = self._base_path / f"{snapshot_id}.json"
        tmp_path = filepath.with_suffix(".tmp")

        try:
            tmp_path.write_text(stored_text)
            os.replace(str(tmp_path), str(filepath))
            status = SnapshotStatus.COMMITTED
        except OSError:
            status = SnapshotStatus.CORRUPTED

        metadata = SnapshotMetadata(
            snapshot_id=snapshot_id,
            version=3,
            ts_ns=ts_ns,
            mode=state.get("mode", "UNKNOWN"),
            tick_count=self._tick_counter,
            content_hash=content_hash,
            ledger_position=state.get("ledger_position", 0),
            size_bytes=len(stored_text),
            status=status,
        )
        self._snapshots.append(metadata)
        self._prune_old_snapshots()
        return metadata

    def load_latest(self) -> tuple[SnapshotMetadata, dict[str, Any]] | None:
        """Load the most recent valid snapshot from disk.

        Returns:
            (metadata, state_dict) or None if no valid snapshot found.
        """
        snapshot_files = sorted(self._base_path.glob("snap_*.json"), reverse=True)
        for filepath in snapshot_files:
            try:
                content = filepath.read_text()
                state = json.loads(content)
                if self._config.verify_on_read:
                    expected_hash = state.get("_content_hash")
                    if expected_hash is not None:
                        # Re-hash just the state fields (keys not prefixed with _)
                        state_only = {k: v for k, v in state.items() if not k.startswith("_")}
                        actual_hash = hashlib.blake2b(
                            json.dumps(state_only, default=str, sort_keys=True).encode(),
                            digest_size=32,
                        ).hexdigest()
                        if actual_hash != expected_hash:
                            continue
                metadata = SnapshotMetadata(
                    snapshot_id=filepath.stem,
                    version=state.get("_version", 3),
                    ts_ns=state.get("_ts_ns", 0),
                    mode=state.get("mode", "UNKNOWN"),
                    tick_count=state.get("_tick_count", 0),
                    content_hash=hashlib.blake2b(content.encode(), digest_size=32).hexdigest(),
                    ledger_position=state.get("ledger_position", 0),
                    size_bytes=len(content),
                    status=SnapshotStatus.COMMITTED,
                )
                return metadata, state
            except (json.JSONDecodeError, OSError):
                continue
        return None

    def list_snapshots(self) -> list[SnapshotMetadata]:
        """List all known snapshots (in-memory registry)."""
        return list(self._snapshots)

    def _prune_old_snapshots(self) -> None:
        """Remove oldest snapshots beyond max_snapshots limit."""
        while len(self._snapshots) > self._config.max_snapshots:
            oldest = self._snapshots.pop(0)
            filepath = self._base_path / f"{oldest.snapshot_id}.json"
            try:
                filepath.unlink(missing_ok=True)
            except OSError:
                pass

    @property
    def snapshot_count(self) -> int:
        """Number of snapshots currently retained."""
        return len(self._snapshots)

    @property
    def last_snapshot(self) -> SnapshotMetadata | None:
        """Most recent snapshot metadata."""
        return self._snapshots[-1] if self._snapshots else None


# Module-level singleton for DI
_MANAGER: SnapshotManager | None = None


def get_snapshot_manager(config: SnapshotConfig | None = None) -> SnapshotManager:
    """Get or create the singleton SnapshotManager."""
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = SnapshotManager(config)
    return _MANAGER


def save_snapshot(state: dict[str, Any]) -> SnapshotMetadata:
    """Module-level convenience: write an immediate snapshot."""
    return get_snapshot_manager().write_snapshot(state)


def save_incremental(state: dict[str, Any]) -> SnapshotMetadata | None:
    """Module-level convenience: tick-based incremental snapshot."""
    return get_snapshot_manager().tick(state)


def restore_latest() -> tuple[SnapshotMetadata, dict[str, Any]] | None:
    """Module-level convenience: load the most recent valid snapshot."""
    return get_snapshot_manager().load_latest()


__all__ = [
    "SnapshotConfig",
    "SnapshotManager",
    "SnapshotMetadata",
    "SnapshotStatus",
    "get_snapshot_manager",
    "restore_latest",
    "save_incremental",
    "save_snapshot",
]

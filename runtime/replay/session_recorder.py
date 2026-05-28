"""Session Recorder — captures all events during a live session (CONVERGENCE PILLAR 4).

Records every event and state transition that occurs during a live
session, producing a replay-capable session recording.

The recording includes:
- All market ticks (ingestion bus output)
- All governance decisions
- All execution intents and fills
- RuntimeSnapshot checkpoints at configurable intervals
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum, auto

from runtime.authority import RuntimeAuthorityStore


class EventCategory(StrEnum):
    """Categories of recorded events."""

    MARKET_TICK = auto()
    DECISION_SIGNAL = auto()
    GOVERNANCE_DECISION = auto()
    EXECUTION_INTENT = auto()
    EXECUTION_FILL = auto()
    STATE_CHECKPOINT = auto()
    HAZARD = auto()
    OPERATOR_ACTION = auto()


@dataclass(frozen=True, slots=True)
class RecordedEvent:
    """A single recorded event with full provenance."""

    sequence: int
    category: EventCategory
    ts_ns: int
    payload: dict[str, object]
    state_version: int
    digest: str  # SHA-256 of payload for integrity


@dataclass(frozen=True, slots=True)
class SessionManifest:
    """Metadata for a session recording."""

    session_id: str
    start_ts_ns: int
    end_ts_ns: int
    total_events: int
    checkpoint_count: int
    final_state_version: int
    integrity_hash: str  # Chain hash of all events


class SessionRecorder:
    """Records all events during a live session.

    Subscribes to RuntimeAuthority changes and records every state
    transition. Also accepts explicit event recording from fabric stages.
    """

    def __init__(
        self,
        *,
        session_id: str,
        store: RuntimeAuthorityStore,
        checkpoint_interval: int = 100,
    ) -> None:
        self._session_id = session_id
        self._store = store
        self._checkpoint_interval = checkpoint_interval
        self._events: list[RecordedEvent] = []
        self._sequence = 0
        self._start_ts_ns = 0
        self._chain_hash = hashlib.sha256(b"genesis").hexdigest()
        self._recording = False

    @property
    def event_count(self) -> int:
        return len(self._events)

    @property
    def recording(self) -> bool:
        return self._recording

    def start(self, ts_ns: int) -> None:
        """Start recording."""
        self._start_ts_ns = ts_ns
        self._recording = True
        # Record initial state checkpoint
        self._record_checkpoint(ts_ns)

    def stop(self, ts_ns: int) -> SessionManifest:
        """Stop recording and produce manifest."""
        self._recording = False
        self._record_checkpoint(ts_ns)

        return SessionManifest(
            session_id=self._session_id,
            start_ts_ns=self._start_ts_ns,
            end_ts_ns=ts_ns,
            total_events=len(self._events),
            checkpoint_count=sum(
                1 for e in self._events if e.category == EventCategory.STATE_CHECKPOINT
            ),
            final_state_version=self._store.version,
            integrity_hash=self._chain_hash,
        )

    def record(
        self,
        *,
        category: EventCategory,
        ts_ns: int,
        payload: dict[str, object],
    ) -> RecordedEvent:
        """Record an event."""
        if not self._recording:
            msg = "Recorder not started"
            raise RuntimeError(msg)

        # Compute payload digest
        payload_str = json.dumps(payload, sort_keys=True, default=str)
        digest = hashlib.sha256(payload_str.encode()).hexdigest()

        # Chain hash
        chain_input = f"{self._chain_hash}:{digest}".encode()
        self._chain_hash = hashlib.sha256(chain_input).hexdigest()

        event = RecordedEvent(
            sequence=self._sequence,
            category=category,
            ts_ns=ts_ns,
            payload=payload,
            state_version=self._store.version,
            digest=digest,
        )
        self._events.append(event)
        self._sequence += 1

        # Auto-checkpoint
        if self._sequence % self._checkpoint_interval == 0:
            self._record_checkpoint(ts_ns)

        return event

    def get_events(self) -> list[RecordedEvent]:
        """Get all recorded events (for replay)."""
        return list(self._events)

    def _record_checkpoint(self, ts_ns: int) -> None:
        """Record a state checkpoint."""
        snap = self._store.snapshot
        payload: dict[str, object] = {
            "version": snap.version,
            "system_mode": snap.system_mode,
            "health_score": snap.health_score,
            "live_execution_blocked": snap.live_execution_blocked,
            "open_positions": snap.open_positions,
            "total_exposure_usd": snap.total_exposure_usd,
            "freeze_active": snap.freeze_active,
            "learning_active": snap.learning_active,
        }

        payload_str = json.dumps(payload, sort_keys=True, default=str)
        digest = hashlib.sha256(payload_str.encode()).hexdigest()
        chain_input = f"{self._chain_hash}:{digest}".encode()
        self._chain_hash = hashlib.sha256(chain_input).hexdigest()

        event = RecordedEvent(
            sequence=self._sequence,
            category=EventCategory.STATE_CHECKPOINT,
            ts_ns=ts_ns,
            payload=payload,
            state_version=snap.version,
            digest=digest,
        )
        self._events.append(event)
        self._sequence += 1

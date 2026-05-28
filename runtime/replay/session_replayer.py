"""Session Replayer — reproduce exact state from recording (CONVERGENCE PILLAR 4).

Given a session recording, replays all events through the same pipeline
and verifies that the resulting state matches the recorded checkpoints.

Replay process:
1. Load recording manifest + events
2. Inject LedgerClock with recorded timestamps
3. Create fresh RuntimeAuthorityStore
4. Feed events through fabric stages
5. At each checkpoint: verify state matches recording
6. Report: IDENTICAL or DIVERGED_AT(step, expected, actual)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, auto

from runtime.authority import RuntimeAuthorityStore
from runtime.replay.session_recorder import (
    EventCategory,
    RecordedEvent,
    SessionManifest,
)


class ReplayStatus(StrEnum):
    """Overall replay result."""

    IDENTICAL = auto()
    DIVERGED = auto()
    INCOMPLETE = auto()
    ERROR = auto()


@dataclass(frozen=True, slots=True)
class Divergence:
    """A point where replay diverged from recording."""

    event_sequence: int
    ts_ns: int
    field: str
    expected: str
    actual: str


@dataclass(frozen=True, slots=True)
class ReplayResult:
    """Result of a replay session."""

    status: ReplayStatus
    events_replayed: int
    checkpoints_verified: int
    divergences: tuple[Divergence, ...]
    final_state_version: int


class SessionReplayer:
    """Replays a recorded session and verifies determinism.

    Creates a fresh RuntimeAuthorityStore and feeds recorded events
    through it, verifying state at each checkpoint.
    """

    def __init__(self) -> None:
        self._store: RuntimeAuthorityStore | None = None

    def replay(
        self,
        *,
        events: list[RecordedEvent],
        manifest: SessionManifest,
    ) -> ReplayResult:
        """Replay a session recording and verify determinism.

        Returns a ReplayResult indicating whether the replay was
        identical to the original session.
        """
        self._store = RuntimeAuthorityStore()
        writer_token = self._store.issue_writer_token("execution_fabric")

        divergences: list[Divergence] = []
        checkpoints_verified = 0
        events_replayed = 0

        for event in events:
            events_replayed += 1

            if event.category == EventCategory.STATE_CHECKPOINT:
                # Verify state matches recording
                checkpoint_divergences = self._verify_checkpoint(event)
                divergences.extend(checkpoint_divergences)
                if not checkpoint_divergences:
                    checkpoints_verified += 1

            elif event.category == EventCategory.MARKET_TICK:
                # Replay market tick by updating state
                writer_token.write(
                    event.ts_ns,
                    last_market_ts_ns=event.ts_ns,
                    market_connected=True,
                )

            elif event.category == EventCategory.EXECUTION_FILL:
                # Replay fill
                payload = event.payload
                positions = int(payload.get("open_positions", 0))
                exposure = float(payload.get("total_exposure_usd", 0.0))
                writer_token.write(
                    event.ts_ns,
                    open_positions=positions,
                    total_exposure_usd=exposure,
                )

            elif event.category == EventCategory.HAZARD:
                payload = event.payload
                code = str(payload.get("code", ""))
                current = self._store.snapshot.active_hazards
                if payload.get("action") == "record":
                    writer_token.write(
                        event.ts_ns,
                        active_hazards=(*current, code),
                    )
                elif payload.get("action") == "clear":
                    writer_token.write(
                        event.ts_ns,
                        active_hazards=tuple(h for h in current if h != code),
                    )

        # Determine overall status
        if divergences:
            status = ReplayStatus.DIVERGED
        elif events_replayed < manifest.total_events:
            status = ReplayStatus.INCOMPLETE
        else:
            status = ReplayStatus.IDENTICAL

        return ReplayResult(
            status=status,
            events_replayed=events_replayed,
            checkpoints_verified=checkpoints_verified,
            divergences=tuple(divergences),
            final_state_version=self._store.version if self._store else 0,
        )

    def _verify_checkpoint(self, event: RecordedEvent) -> list[Divergence]:
        """Verify current state matches a checkpoint."""
        if self._store is None:
            return []

        snap = self._store.snapshot
        payload = event.payload
        divergences: list[Divergence] = []

        # Check each recorded field
        checks: list[tuple[str, object, object]] = [
            ("system_mode", payload.get("system_mode"), snap.system_mode),
            ("health_score", payload.get("health_score"), snap.health_score),
            (
                "live_execution_blocked",
                payload.get("live_execution_blocked"),
                snap.live_execution_blocked,
            ),
            ("open_positions", payload.get("open_positions"), snap.open_positions),
            ("freeze_active", payload.get("freeze_active"), snap.freeze_active),
            ("learning_active", payload.get("learning_active"), snap.learning_active),
        ]

        for field_name, expected, actual in checks:
            if expected is not None and str(expected) != str(actual):
                divergences.append(
                    Divergence(
                        event_sequence=event.sequence,
                        ts_ns=event.ts_ns,
                        field=field_name,
                        expected=str(expected),
                        actual=str(actual),
                    )
                )

        return divergences

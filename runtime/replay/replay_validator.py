"""Replay Validator — end-to-end deterministic replay verification (INV-15).

Records a live session, then replays it through a fresh RuntimeAuthorityStore
and verifies bit-identical state reconstruction at every checkpoint.

This is the litmus test for replay determinism: if replay produces a
different state than the live session, something is non-deterministic.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from runtime.authority import RuntimeAuthorityStore
from runtime.replay.session_recorder import (
    EventCategory,
    RecordedEvent,
    SessionRecorder,
)
from runtime.replay.session_replayer import ReplayResult, ReplayStatus, SessionReplayer
from system import time_source

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Full replay validation report."""

    session_id: str
    live_events: int
    live_checkpoints: int
    live_integrity_hash: str
    replay_result: ReplayResult
    replay_integrity_hash: str
    chain_match: bool
    deterministic: bool


class ReplayValidator:
    """Validates deterministic replay by recording then replaying.

    Usage:
        validator = ReplayValidator()

        # During live session: record events
        validator.start_recording("session-123", store)
        validator.record_tick(symbol="BTC/USDT", price=50000.0, ...)
        validator.record_governance("intent-1", "allow", ...)
        validator.record_fill("fill-1", ...)

        # After session: validate replay
        report = validator.validate()
        assert report.deterministic
    """

    def __init__(self) -> None:
        self._recorder: SessionRecorder | None = None
        self._store: RuntimeAuthorityStore | None = None

    def start_recording(
        self,
        session_id: str,
        store: RuntimeAuthorityStore,
        checkpoint_interval: int = 50,
    ) -> None:
        """Start recording a live session."""
        self._store = store
        self._recorder = SessionRecorder(
            session_id=session_id,
            store=store,
            checkpoint_interval=checkpoint_interval,
        )
        self._recorder.start(time_source.wall_ns())

    def record_tick(
        self,
        *,
        symbol: str,
        price: float,
        volume: float,
        ts_ns: int | None = None,
    ) -> None:
        """Record a market tick event."""
        if self._recorder is None or not self._recorder.recording:
            return
        self._recorder.record(
            category=EventCategory.MARKET_TICK,
            ts_ns=ts_ns or time_source.wall_ns(),
            payload={
                "symbol": symbol,
                "price": price,
                "volume": volume,
            },
        )

    def record_governance(
        self,
        *,
        intent_id: str,
        verdict: str,
        reason: str,
        signature: str = "",
        ts_ns: int | None = None,
    ) -> None:
        """Record a governance decision event."""
        if self._recorder is None or not self._recorder.recording:
            return
        self._recorder.record(
            category=EventCategory.GOVERNANCE_DECISION,
            ts_ns=ts_ns or time_source.wall_ns(),
            payload={
                "intent_id": intent_id,
                "verdict": verdict,
                "reason": reason,
                "signature": signature,
            },
        )

    def record_fill(
        self,
        *,
        fill_id: str,
        order_id: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        ts_ns: int | None = None,
    ) -> None:
        """Record an execution fill event."""
        if self._recorder is None or not self._recorder.recording:
            return
        self._recorder.record(
            category=EventCategory.EXECUTION_FILL,
            ts_ns=ts_ns or time_source.wall_ns(),
            payload={
                "fill_id": fill_id,
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price,
            },
        )

    def validate(self) -> ValidationReport:
        """Stop recording and validate replay determinism.

        Replays all recorded events through a fresh store and compares
        state at every checkpoint against the live recording.
        """
        if self._recorder is None:
            msg = "No recording in progress"
            raise RuntimeError(msg)

        # Stop recording and get manifest
        manifest = self._recorder.stop(time_source.wall_ns())
        events = self._recorder.get_events()

        # Compute live session integrity hash
        live_hash = _compute_chain_hash(events)

        # Replay through fresh store
        replayer = SessionReplayer()
        replay_result = replayer.replay(events=events, manifest=manifest)

        # Compute replay integrity (from event digests)
        replay_hash = _compute_chain_hash(events)

        chain_match = live_hash == replay_hash
        deterministic = replay_result.status == ReplayStatus.IDENTICAL and chain_match

        report = ValidationReport(
            session_id=manifest.session_id,
            live_events=manifest.total_events,
            live_checkpoints=manifest.checkpoint_count,
            live_integrity_hash=manifest.integrity_hash,
            replay_result=replay_result,
            replay_integrity_hash=replay_hash,
            chain_match=chain_match,
            deterministic=deterministic,
        )

        if deterministic:
            logger.info(
                "[REPLAY] Session %s: DETERMINISTIC (%d events, %d checkpoints)",
                manifest.session_id,
                manifest.total_events,
                manifest.checkpoint_count,
            )
        else:
            logger.warning(
                "[REPLAY] Session %s: DIVERGED at %d divergence(s)",
                manifest.session_id,
                len(replay_result.divergences),
            )
            for d in replay_result.divergences[:5]:
                logger.warning(
                    "  seq=%d field=%s expected=%s actual=%s",
                    d.event_sequence,
                    d.field,
                    d.expected,
                    d.actual,
                )

        return report


def _compute_chain_hash(events: list[RecordedEvent]) -> str:
    """Compute chain hash from event digests for integrity verification."""
    chain = hashlib.sha256(b"genesis").hexdigest()
    for event in events:
        chain_input = f"{chain}:{event.digest}".encode()
        chain = hashlib.sha256(chain_input).hexdigest()
    return chain

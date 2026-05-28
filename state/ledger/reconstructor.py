"""state/ledger/reconstructor.py
DIX VISION v42.2 — Ledger State Reconstructor

Replays a ledger stream slice to reconstruct system state at a given
point in time. Used by the calibration pipeline (INV-53), offline
analytics, and governance audit tools.

The reconstructor is OFFLINE-only — it must never be called from
any hot-path module. It loads events from the EventStore and folds
them through registered reducer functions.

Deterministic (INV-15): same ledger slice always produces same output.
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from typing import Any, Callable

from state.ledger.event_store import LedgerEvent, get_event_store


@dataclass(frozen=True, slots=True)
class ReconstructionResult:
    """Output of a ledger reconstruction run."""
    stream_kind: str
    since_ts_ns: int
    until_ts_ns: int
    event_count: int
    checksum: str       # SHA256 of all event_hashes in order
    state: dict[str, Any]
    ts_ns: int


# Type alias: reducer takes (state, event) → new state
ReducerFn = Callable[[dict[str, Any], LedgerEvent], dict[str, Any]]


class LedgerReconstructor:
    """
    Replays ledger events through registered reducers to rebuild state.

    Thread-safe. Reducers are pure functions — same event → same mutation.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reducers: dict[str, list[ReducerFn]] = {}

    def register_reducer(self, stream_kind: str, fn: ReducerFn) -> None:
        """Register a reducer for a stream kind."""
        with self._lock:
            self._reducers.setdefault(stream_kind, []).append(fn)

    def reconstruct(
        self,
        stream_kind: str,
        since_ts_ns: int = 0,
        until_ts_ns: int | None = None,
        limit: int | None = None,
        initial_state: dict[str, Any] | None = None,
        ts_ns: int = 0,
    ) -> ReconstructionResult:
        """
        Replay events from the ledger and fold them into state.

        Args:
            stream_kind:    Stream to replay (MARKET, SYSTEM, etc.)
            since_ts_ns:    Start of replay window (inclusive).
            until_ts_ns:    End of replay window (inclusive, None = all).
            limit:          Maximum events to process.
            initial_state:  Starting state dict (None = empty dict).

        Returns:
            ReconstructionResult with the final state and checksum.
        """
        store = get_event_store()
        events = store.query(
            stream_kind=stream_kind,
            since_ts_ns=since_ts_ns,
            limit=limit,
        )

        if until_ts_ns is not None:
            events = [e for e in events if e.ts_ns <= until_ts_ns]

        with self._lock:
            reducers = list(self._reducers.get(stream_kind, []))

        state: dict[str, Any] = dict(initial_state) if initial_state else {}
        hash_parts: list[str] = []

        for evt in events:
            for fn in reducers:
                state = fn(state, evt)
            hash_parts.append(evt.event_hash)

        checksum = hashlib.sha256(
            "|".join(hash_parts).encode()
        ).hexdigest() if hash_parts else ""

        actual_until = events[-1].ts_ns if events else since_ts_ns

        return ReconstructionResult(
            stream_kind=stream_kind,
            since_ts_ns=since_ts_ns,
            until_ts_ns=actual_until,
            event_count=len(events),
            checksum=checksum,
            state=state,
            ts_ns=ts_ns,
        )

    def verify_determinism(
        self,
        stream_kind: str,
        since_ts_ns: int = 0,
        until_ts_ns: int | None = None,
        ts_ns: int = 0,
    ) -> bool:
        """
        Run reconstruction twice and confirm identical checksums.

        Returns True if both runs produced the same checksum (INV-15).
        """
        r1 = self.reconstruct(stream_kind, since_ts_ns, until_ts_ns, ts_ns=ts_ns)
        r2 = self.reconstruct(stream_kind, since_ts_ns, until_ts_ns, ts_ns=ts_ns)
        return r1.checksum == r2.checksum


# Singleton factory
_instance: LedgerReconstructor | None = None
_lock = threading.Lock()


def get_ledger_reconstructor() -> LedgerReconstructor:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = LedgerReconstructor()
    return _instance


__all__ = [
    "LedgerReconstructor",
    "ReconstructionResult",
    "ReducerFn",
    "get_ledger_reconstructor",
]

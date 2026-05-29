"""state.memory.replay — MemoryReplayEngine.

Replays a time-range slice of the CognitionTimeline in strict ts_ns
order, yielding MemoryRecord-like dicts for downstream consumers.

INV-15: all timestamps are read from the stored records (caller-supplied
at write time); the engine adds no wall-clock reads.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from state.memory.contracts import MemoryKind

_logger = logging.getLogger(__name__)


class ReplaySession:
    """A single time-range replay cursor over the CognitionTimeline.

    Records are fetched in batches and yielded oldest-first.
    """

    def __init__(
        self,
        *,
        session_id: str,
        since_ns:   int,
        until_ns:   int,
        kinds:      list[str] | None = None,
        batch_size: int = 100,
    ) -> None:
        self.session_id = session_id
        self.since_ns   = since_ns
        self.until_ns   = until_ns
        self.kinds      = kinds
        self.batch_size = batch_size
        self._cursor:   int = since_ns
        self._done:     bool = False
        self._emitted:  int = 0

    def __iter__(self) -> Iterator[dict]:
        return self._generate()

    def _generate(self) -> Iterator[dict]:
        try:
            from state.memory.timeline import get_cognition_timeline
            tl = get_cognition_timeline()
            while not self._done:
                batch = tl.query(
                    since_ns=self._cursor,
                    until_ns=self.until_ns,
                    kinds=self.kinds,
                    limit=self.batch_size,
                )
                if not batch:
                    self._done = True
                    break
                # timeline returns newest-first; reverse for chronological replay
                batch_sorted = sorted(batch, key=lambda r: r["ts_ns"])
                for row in batch_sorted:
                    self._emitted += 1
                    yield row
                last_ts = batch_sorted[-1]["ts_ns"]
                if last_ts >= self.until_ns or len(batch) < self.batch_size:
                    self._done = True
                    break
                self._cursor = last_ts + 1
        except Exception as exc:
            _logger.debug("replay.session error: %s", exc)

    @property
    def done(self) -> bool:
        return self._done

    @property
    def emitted(self) -> int:
        return self._emitted


class MemoryReplayEngine:
    """Creates and tracks replay sessions over the CognitionTimeline."""

    def __init__(self) -> None:
        self._lock:     threading.Lock              = threading.Lock()
        self._sessions: dict[str, ReplaySession]   = {}
        self._total:    int                         = 0

    def start_replay(
        self,
        *,
        session_id: str,
        since_ns:   int,
        until_ns:   int,
        kinds:      list[str] | None = None,
    ) -> ReplaySession:
        """Create a new ReplaySession. Replaces any existing session with same id."""
        session = ReplaySession(
            session_id=session_id,
            since_ns=since_ns,
            until_ns=until_ns,
            kinds=kinds,
        )
        with self._lock:
            self._sessions[session_id] = session
            self._total += 1
        return session

    def get_session(self, session_id: str) -> ReplaySession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def list_sessions(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "session_id": s.session_id,
                    "since_ns":   s.since_ns,
                    "until_ns":   s.until_ns,
                    "done":       s.done,
                    "emitted":    s.emitted,
                }
                for s in self._sessions.values()
            ]

    def snapshot(self) -> dict:
        with self._lock:
            active = sum(1 for s in self._sessions.values() if not s.done)
            return {
                "active":           True,
                "total_sessions":   self._total,
                "active_sessions":  active,
                "completed_sessions": self._total - active,
            }


_singleton: MemoryReplayEngine | None = None
_lock = threading.Lock()


def get_memory_replay_engine() -> MemoryReplayEngine:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = MemoryReplayEngine()
    return _singleton


__all__ = ["ReplaySession", "MemoryReplayEngine", "get_memory_replay_engine"]

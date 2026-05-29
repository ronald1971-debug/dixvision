"""runtime.unified_fabric.replay — FabricReplayStream.

Deterministic replay of the unified event fabric from its SQLite log.

Replay semantics (INV-15):
- Events are replayed in strict sequence ASC order (total order within replay)
- ts_ns values are the originals from the persisted events (never re-clocked)
- Each replayed event gets a REPLAY tag and a new replay_session_id
- Replay does NOT re-publish to live subscribers (read-only by default)
  unless replay_live=True is set (for simulation-mode testing only)

Use cases:
- Operator audit: "show me everything that happened between T1 and T2"
- Root cause: "replay from the RISK_BREACH backwards to find the chain"
- Simulation: "replay a recorded session against a new strategy version"
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Iterator

_logger = logging.getLogger(__name__)

ReplayHandler = Callable[[dict[str, Any]], None]


class ReplaySession:
    """A single replay cursor over the FabricPersistence event log."""

    def __init__(
        self,
        *,
        session_id:   str,
        since_ns:     int,
        until_ns:     int,
        domain:       str | None = None,
        event_type:   str | None = None,
        trace_id:     str | None = None,
        batch_size:   int = 200,
        replay_live:  bool = False,
    ) -> None:
        self.session_id  = session_id
        self.since_ns    = since_ns
        self.until_ns    = until_ns
        self.domain      = domain
        self.event_type  = event_type
        self.trace_id    = trace_id
        self.batch_size  = batch_size
        self.replay_live = replay_live

        self._cursor:   int  = 0   # last sequence seen
        self._done:     bool = False
        self._emitted:  int  = 0
        self._handlers: list[ReplayHandler] = []

    def add_handler(self, handler: ReplayHandler) -> None:
        self._handlers.append(handler)

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return self._generate()

    def _generate(self) -> Iterator[dict[str, Any]]:
        try:
            from runtime.unified_fabric.persistence import get_fabric_persistence
            fp = get_fabric_persistence()
            while not self._done:
                batch = fp.replay(
                    since_ns   = self.since_ns if self._cursor == 0 else None,
                    until_ns   = self.until_ns,
                    domain     = self.domain,
                    event_type = self.event_type,
                    trace_id   = self.trace_id,
                    limit      = self.batch_size,
                )
                # filter cursor (sequence-based pagination)
                if self._cursor > 0:
                    batch = [r for r in batch if r["sequence"] > self._cursor]
                if not batch:
                    self._done = True
                    break
                for row in batch:
                    row["_replay_session"] = self.session_id
                    row["_replayed"] = True
                    self._emitted += 1
                    for handler in self._handlers:
                        try:
                            handler(row)
                        except Exception as exc:
                            _logger.debug("replay handler error: %s", exc)
                    yield row
                self._cursor = batch[-1]["sequence"]
                if len(batch) < self.batch_size:
                    self._done = True
        except Exception as exc:
            _logger.debug("ReplaySession._generate error: %s", exc)
            self._done = True

    @property
    def done(self) -> bool:
        return self._done

    @property
    def emitted(self) -> int:
        return self._emitted


class FabricReplayStream:
    """Creates and manages deterministic replay sessions."""

    def __init__(self) -> None:
        self._lock:     threading.Lock           = threading.Lock()
        self._sessions: dict[str, ReplaySession] = {}
        self._total:    int = 0

    def start(
        self,
        *,
        session_id:  str,
        since_ns:    int,
        until_ns:    int,
        domain:      str | None = None,
        event_type:  str | None = None,
        trace_id:    str | None = None,
        replay_live: bool = False,
    ) -> ReplaySession:
        session = ReplaySession(
            session_id  = session_id,
            since_ns    = since_ns,
            until_ns    = until_ns,
            domain      = domain,
            event_type  = event_type,
            trace_id    = trace_id,
            replay_live = replay_live,
        )
        with self._lock:
            self._sessions[session_id] = session
            self._total += 1
        return session

    def get(self, session_id: str) -> ReplaySession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def list_sessions(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "session_id":  s.session_id,
                    "since_ns":    s.since_ns,
                    "until_ns":    s.until_ns,
                    "domain":      s.domain,
                    "event_type":  s.event_type,
                    "trace_id":    s.trace_id,
                    "done":        s.done,
                    "emitted":     s.emitted,
                    "replay_live": s.replay_live,
                }
                for s in self._sessions.values()
            ]

    def snapshot(self) -> dict:
        with self._lock:
            active = sum(1 for s in self._sessions.values() if not s.done)
            return {
                "active":             True,
                "total_sessions":     self._total,
                "active_sessions":    active,
                "completed_sessions": self._total - active,
            }


_singleton: FabricReplayStream | None = None
_lock = threading.Lock()


def get_fabric_replay_stream() -> FabricReplayStream:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = FabricReplayStream()
    return _singleton


__all__ = ["ReplaySession", "FabricReplayStream", "get_fabric_replay_stream"]

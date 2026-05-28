"""core.time_source — Canonical TimeAuthority Protocol (BUILD-DIRECTIVE §4).

Every hot-path module accepts a :class:`TimeAuthority` via DI rather than
calling ``time.time_ns()`` directly. The B-CLOCK lint rule bans raw clock
calls outside ``system/time_source.py`` and this module.

Three implementations:
- :class:`WallClock` — production (delegates to ``system.time_source``).
- :class:`FixedClock` — tests / deterministic replay (INV-15).
- :class:`LedgerClock` — replays timestamps from a recorded ledger stream.

Usage::

    from core.time_source import TimeAuthority, WallClock, FixedClock

    def my_hot_path(clock: TimeAuthority) -> int:
        return clock.now_ns()

    # Production
    clock = WallClock()

    # Tests (deterministic)
    clock = FixedClock(seed_ns=1_000_000_000)
"""

from __future__ import annotations

import time
from typing import Protocol

__all__ = (
    "TimeAuthority",
    "WallClock",
    "FixedClock",
    "LedgerClock",
)


class TimeAuthority(Protocol):
    """Protocol for all clock sources in DIX VISION.

    Implementations MUST be deterministic for replay (INV-15) or clearly
    documented as wall-clock sources used only at the bus boundary.
    """

    def now_ns(self) -> int:
        """Return current time in nanoseconds (monotonic or wall)."""
        ...


class WallClock:
    """Production clock — reads the real system wall clock.

    Delegates to ``system.time_source.wall_ns()`` for epoch-aligned
    nanoseconds. Used at the bus boundary where the system samples the
    world.
    """

    __slots__ = ()

    def now_ns(self) -> int:  # noqa: PLR6301
        """Wall-clock nanoseconds since Unix epoch."""
        return time.time_ns()

    def __repr__(self) -> str:
        return "WallClock()"


class FixedClock:
    """Deterministic clock for tests and replay (INV-15).

    Each call to ``now_ns()`` advances by ``step_ns`` nanoseconds,
    producing a fully deterministic, monotonically increasing sequence.
    """

    __slots__ = ("_current_ns", "_step_ns")

    def __init__(self, *, seed_ns: int = 1_000_000_000, step_ns: int = 1_000_000) -> None:
        self._current_ns = seed_ns
        self._step_ns = step_ns

    def now_ns(self) -> int:
        """Return next deterministic timestamp."""
        ts = self._current_ns
        self._current_ns += self._step_ns
        return ts

    def peek_ns(self) -> int:
        """Return current value without advancing."""
        return self._current_ns

    def reset(self, seed_ns: int = 1_000_000_000) -> None:
        """Reset clock to a specific value."""
        self._current_ns = seed_ns

    def __repr__(self) -> str:
        return f"FixedClock(current_ns={self._current_ns}, step_ns={self._step_ns})"


class LedgerClock:
    """Replay clock that yields timestamps from a recorded ledger stream.

    Used for deterministic replay from the authority ledger. If the stream
    is exhausted, raises ``StopIteration``.
    """

    __slots__ = ("_timestamps", "_index")

    def __init__(self, timestamps: tuple[int, ...]) -> None:
        self._timestamps = timestamps
        self._index = 0

    def now_ns(self) -> int:
        """Return next ledger timestamp."""
        if self._index >= len(self._timestamps):
            msg = "LedgerClock exhausted — no more recorded timestamps"
            raise StopIteration(msg)
        ts = self._timestamps[self._index]
        self._index += 1
        return ts

    @property
    def remaining(self) -> int:
        """Number of timestamps remaining in the stream."""
        return len(self._timestamps) - self._index

    def __repr__(self) -> str:
        return f"LedgerClock(remaining={self.remaining}, total={len(self._timestamps)})"

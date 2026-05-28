"""core.contracts.time — Time Protocol Contracts (Build Directive §4 / B33).

Defines the structural contracts for time authorities. The concrete
implementations live in ``core/time_source.py``. All hot-path modules accept a
TimeAuthority via DI — no raw ``time.time*`` or ``datetime.now*`` calls allowed
outside designated boundary modules (B33 lint rule enforced).

Three implementations exist:
- WallClock: production (at bus boundary only)
- FixedClock: tests / deterministic replay (INV-15)
- LedgerClock: replays timestamps from recorded event streams
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@runtime_checkable
class TimeAuthority(Protocol):
    """Protocol: all clock sources must satisfy this contract.

    INV-15 (replay determinism) requires that no hot-path module reads a
    wall clock directly. Instead, they accept a TimeAuthority and call
    ``now_ns()``. During replay, a FixedClock or LedgerClock is injected
    to reproduce identical event ordering.
    """

    def now_ns(self) -> int:
        """Return current time in nanoseconds.

        For WallClock: epoch-aligned nanoseconds (time.time_ns()).
        For FixedClock: deterministic monotonic sequence.
        For LedgerClock: next recorded timestamp from event stream.
        """
        ...


@runtime_checkable
class MonotonicAuthority(Protocol):
    """Protocol: monotonic clock for latency measurement.

    Unlike TimeAuthority (wall clock), this provides relative duration
    measurement that is immune to wall-clock adjustments.
    """

    def monotonic_ns(self) -> int:
        """Return monotonic nanoseconds for duration measurement."""
        ...


@dataclass(frozen=True, slots=True)
class TimeBounds:
    """Time window for queries and replay slicing.

    Used by the ledger reader and replay engine to scope event ranges.
    """

    start_ns: int
    end_ns: int

    def __post_init__(self) -> None:
        if self.start_ns < 0:
            msg = "start_ns must be >= 0"
            raise ValueError(msg)
        if self.end_ns < self.start_ns:
            msg = "end_ns must be >= start_ns"
            raise ValueError(msg)

    @property
    def duration_ns(self) -> int:
        """Duration of the time window in nanoseconds."""
        return self.end_ns - self.start_ns

    @property
    def duration_ms(self) -> float:
        """Duration in milliseconds."""
        return self.duration_ns / 1_000_000

    @property
    def duration_s(self) -> float:
        """Duration in seconds."""
        return self.duration_ns / 1_000_000_000

    def contains(self, ts_ns: int) -> bool:
        """Check whether a timestamp falls within this window."""
        return self.start_ns <= ts_ns <= self.end_ns


@dataclass(frozen=True, slots=True)
class TimeSequence:
    """Ordered sequence of timestamps with validation.

    Used by LedgerClock to store a replay stream and by the replay engine
    to validate monotonic ordering of events.
    """

    timestamps: tuple[int, ...]

    def __post_init__(self) -> None:
        for i in range(1, len(self.timestamps)):
            if self.timestamps[i] < self.timestamps[i - 1]:
                msg = f"Non-monotonic at index {i}: {self.timestamps[i]} < {self.timestamps[i - 1]}"
                raise ValueError(msg)

    def __len__(self) -> int:
        return len(self.timestamps)

    @property
    def bounds(self) -> TimeBounds | None:
        """Return the time bounds of this sequence, or None if empty."""
        if not self.timestamps:
            return None
        return TimeBounds(start_ns=self.timestamps[0], end_ns=self.timestamps[-1])

    def slice(self, bounds: TimeBounds) -> TimeSequence:
        """Return a sub-sequence within the given bounds."""
        filtered = tuple(ts for ts in self.timestamps if bounds.contains(ts))
        return TimeSequence(timestamps=filtered)


__all__ = [
    "MonotonicAuthority",
    "TimeBounds",
    "TimeAuthority",
    "TimeSequence",
]

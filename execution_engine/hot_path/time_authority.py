"""execution_engine.hot_path.time_authority — Monotonic clock authority (INV-15 / T0-04).

The hot path MUST obtain all timestamps through this module — never through
``time.monotonic_ns`` / ``time.time_ns`` directly. This single chokepoint
enables deterministic replay: in replay mode :meth:`TimeAuthority.now_ns`
returns the injected timestamp unchanged, so two replays over the same
input stream produce byte-identical outputs (INV-15 / TEST-01 / B-CLOCK).

Design constraints (T1 hot-path purity):
* No imports from governance_engine, system_engine, intelligence_engine,
  evolution_engine, or learning_engine.
* :func:`get_time_authority` uses double-checked locking so the singleton is
  safe to use from concurrent threads without paying a lock on every tick.
* In live mode :meth:`now_ns` returns ``time.monotonic_ns()`` — a lock-free
  C-level call.
* :meth:`wall_ns` is declared *non-deterministic*: callers that need epoch-
  aligned timestamps for audit ledger rows may call it, but the hot path
  itself must not depend on wall time (NTP can jump — INV-58).
"""

from __future__ import annotations

import threading


class TimeAuthority:
    """Monotonic clock authority for the hot path.

    Lifecycle:
      * In *live mode* (the default), :meth:`now_ns` delegates to
        ``time.monotonic_ns()``.
      * After :meth:`set_replay_ts` is called the authority enters
        *replay mode* and :meth:`now_ns` returns the injected
        timestamp unchanged until :meth:`set_replay_ts` is called
        again with a new value, or ``None`` to exit replay mode.

    ``__slots__`` keeps the per-instance memory footprint small and
    prevents accidental attribute creation on the hot path.
    """

    __slots__ = ("_replay_ts", "_lock")

    def __init__(self) -> None:
        self._replay_ts: int | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Hot-path read API
    # ------------------------------------------------------------------

    def now_ns(self) -> int:
        """Return the current monotonic timestamp in nanoseconds.

        In live mode: ``time.monotonic_ns()`` — lock-free, no allocation.
        In replay mode: the last value injected via :meth:`set_replay_ts`.

        T1-pure: no IO, no allocation, no cross-engine import.
        """
        ts = self._replay_ts
        if ts is not None:
            return ts
        import time  # noqa: PLC0415 — lazy: keeps module-level import-free for INV-15
        return time.monotonic_ns()

    def wall_ns(self) -> int:  # noqa: PLR6301 — declared non-deterministic
        """Wall-clock nanoseconds since Unix epoch.

        **NON-DETERMINISTIC.** Use only for ledger audit rows and operator
        metrics — never for hot-path logic (INV-58 / B-CLOCK).
        """
        import time  # noqa: PLC0415
        return time.time_ns()

    # ------------------------------------------------------------------
    # Replay control API (called by the replay harness, not the hot path)
    # ------------------------------------------------------------------

    def set_replay_ts(self, ts_ns: int | None) -> None:
        """Inject a timestamp for deterministic replay.

        Args:
            ts_ns: Nanosecond timestamp to return from :meth:`now_ns`.
                   Pass ``None`` to exit replay mode and resume live clock.
        """
        if ts_ns is not None and not isinstance(ts_ns, int):
            raise TypeError(f"TimeAuthority.set_replay_ts: ts_ns must be int | None, got {type(ts_ns).__name__}")
        if isinstance(ts_ns, int) and ts_ns < 0:
            raise ValueError(f"TimeAuthority.set_replay_ts: ts_ns must be >= 0, got {ts_ns!r}")
        with self._lock:
            self._replay_ts = ts_ns

    @property
    def is_replay_mode(self) -> bool:
        """True when the authority is operating in replay mode."""
        return self._replay_ts is not None


# ---------------------------------------------------------------------------
# Process-wide singleton — double-checked locking
# ---------------------------------------------------------------------------

_singleton_lock = threading.Lock()
_singleton: TimeAuthority | None = None


def get_time_authority() -> TimeAuthority:
    """Return the process-wide :class:`TimeAuthority` singleton.

    Thread-safe via double-checked locking. The first call constructs
    the instance; subsequent calls return the cached instance without
    acquiring the lock.
    """
    global _singleton  # noqa: PLW0603
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = TimeAuthority()
    return _singleton


__all__ = [
    "TimeAuthority",
    "get_time_authority",
]

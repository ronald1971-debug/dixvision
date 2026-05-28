"""execution_engine.hot_path.fast_risk_cache — Ultra-low-latency risk snapshot cache.

The hot path queries risk limits without blocking on the main risk engine
thread. This module implements a copy-on-write snapshot cache: the risk engine
writes atomically via :meth:`FastRiskCache.update`; the hot path reads the
snapshot without a lock (lock-free read via a reference swap).

Design constraints (T1 hot-path purity):
* No imports from governance_engine, system_engine, intelligence_engine,
  evolution_engine, or learning_engine.
* :meth:`FastRiskCache.get` never acquires a lock — it reads a single
  reference assignment, which is atomic in CPython's GIL model.
* :meth:`FastRiskCache.update` acquires a write lock to prevent concurrent
  writers clobbering each other, but never blocks the hot-path reader.
* :attr:`RiskSnapshot` is frozen + slotted: immutable, no heap allocation
  on read, hashable for ledger pinning (INV-15).

INV-15 / B-CLOCK:
  ``ts_ns`` in :class:`RiskSnapshot` must be supplied by the caller
  (risk engine). The cache never reads a clock itself.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from system import time_source


@dataclass(frozen=True, slots=True)
class RiskSnapshot:
    """Immutable risk limit snapshot distributed to the hot path.

    Written by the risk engine; consumed read-only by :class:`FastRiskCache`
    and the hot-path gate.

    Attributes:
        ts_ns: Monotonic nanosecond timestamp of when this snapshot was
            produced (TimeAuthority chokepoint, B-CLOCK).
        max_position_usd: Maximum gross exposure per symbol in USD.
        max_daily_loss_usd: Maximum allowable daily loss in USD (positive).
        current_exposure_usd: Current aggregate gross exposure in USD.
        daily_pnl: Realised + unrealised P&L since session start (signed).
        kill_switch_active: When True the hot path must reject all orders.
    """

    ts_ns: int
    max_position_usd: float
    max_daily_loss_usd: float
    current_exposure_usd: float
    daily_pnl: float
    kill_switch_active: bool


class FastRiskCache:
    """Copy-on-write risk snapshot cache for the hot path.

    The risk engine calls :meth:`update` at whatever cadence it refreshes
    limits (typically every few hundred milliseconds). The hot path calls
    :meth:`get` (lock-free) and :meth:`passes_fast_check` (lock-free) on
    every tick.

    Thread safety:
        * :meth:`get` — lock-free reference read; safe to call from any
          thread at any frequency.
        * :meth:`update` — acquires ``_write_lock`` to serialise concurrent
          writers; never blocks :meth:`get`.

    ``__slots__`` keeps the per-instance memory footprint small.
    """

    __slots__ = ("_snapshot", "_write_lock")

    def __init__(self) -> None:
        self._snapshot: RiskSnapshot | None = None
        self._write_lock = threading.Lock()

    def update(self, snapshot: RiskSnapshot) -> None:
        """Atomically replace the cached snapshot.

        Called by the risk engine after it recomputes limits. The
        assignment is a single pointer swap — :meth:`get` never sees a
        partially-constructed object.

        Args:
            snapshot: The new risk limit snapshot to publish to the hot path.
        """
        if not isinstance(snapshot, RiskSnapshot):
            raise TypeError(
                f"FastRiskCache.update: expected RiskSnapshot, got {type(snapshot).__name__}"
            )
        with self._write_lock:
            self._snapshot = snapshot

    def get(self) -> RiskSnapshot | None:
        """Return the most recent risk snapshot, or None if not yet populated.

        Lock-free read — safe to call on the hot path at maximum tick rate.
        In CPython the attribute read is atomic under the GIL.
        """
        return self._snapshot

    def is_stale(self, max_age_ns: int) -> bool:
        """Return True if the cached snapshot is older than ``max_age_ns``.

        A missing snapshot is always considered stale.

        Args:
            max_age_ns: Maximum acceptable snapshot age in nanoseconds.
        """
        snap = self._snapshot
        if snap is None:
            return True
        age = time_source.now_ns() - snap.ts_ns
        return age > max_age_ns

    def passes_fast_check(self, order_usd: float) -> bool:
        """Return True if ``order_usd`` fits within the cached risk limits.

        Performs a lightweight pre-flight check without blocking:

        1. If no snapshot is present, reject (fail-safe).
        2. If the kill switch is active, reject.
        3. If ``current_exposure_usd + order_usd`` would exceed
           ``max_position_usd``, reject.
        4. If ``daily_pnl`` is already worse than ``-max_daily_loss_usd``,
           reject (loss limit already breached).

        This check is intentionally conservative — the authoritative risk
        decision is made by the governance engine on the slow path.

        Args:
            order_usd: Estimated notional value of the proposed order in USD.

        Returns:
            True if the order passes the fast risk gate; False otherwise.
        """
        snap = self._snapshot
        if snap is None:
            return False
        if snap.kill_switch_active:
            return False
        if snap.current_exposure_usd + order_usd > snap.max_position_usd:
            return False
        if snap.daily_pnl < -snap.max_daily_loss_usd:
            return False
        return True


# ---------------------------------------------------------------------------
# Process-wide singleton — double-checked locking
# ---------------------------------------------------------------------------

_singleton_lock = threading.Lock()
_singleton: FastRiskCache | None = None


def get_fast_risk_cache() -> FastRiskCache:
    """Return the process-wide :class:`FastRiskCache` singleton.

    Thread-safe via double-checked locking. The first call constructs
    the instance; subsequent calls return the cached instance without
    acquiring the lock.
    """
    global _singleton  # noqa: PLW0603
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = FastRiskCache()
    return _singleton


__all__ = [
    "FastRiskCache",
    "RiskSnapshot",
    "get_fast_risk_cache",
]

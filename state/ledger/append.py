"""
state/ledger/append.py
DIX VISION v42.2 — High-level append API with type-safe stream routing.

Provides typed wrappers around EventStore.append for each canonical stream kind.
Each function resolves the singleton EventStore and appends a single event.

AppendBatch is a context manager that buffers multiple appends and commits them
atomically (within a single SQLite transaction, as close as SQLite/WAL allows).

Stream kinds (must match event_types.py):
  MARKET     — tick, orderbook, trade, OHLCV events
  SYSTEM     — startup, shutdown, mode transitions, health checks
  GOVERNANCE — COGOV / OPGOV / SYSGOV / FINGOV decision events
  HAZARD     — HAZ_01..HAZ_15, runtime hazard events
  AUTHORITY  — mode locks, strategy approvals, operator overrides

Authority constraints (manifest §H1):
  * This module is a thin wrapper — it never constructs LedgerEvent directly.
    All persistence is delegated to get_event_store().append().
  * Callers in the intelligence, execution, and governance engines reach
    only this surface; they do not import event_store directly (L2 rule).
  * AppendBatch uses BEGIN DEFERRED / COMMIT via the event_store connection
    to guarantee ordering within the batch. On exception it rolls back.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any, Generator

from state.ledger.event_store import LedgerEvent, get_event_store


# ---------------------------------------------------------------------------
# Stream-kind constants (mirrors event_types.StreamKind values)
# ---------------------------------------------------------------------------

_MARKET = "MARKET"
_SYSTEM = "SYSTEM"
_GOVERNANCE = "GOVERNANCE"
_HAZARD = "HAZARD"
_AUTHORITY = "AUTHORITY"


# ---------------------------------------------------------------------------
# Typed append helpers
# ---------------------------------------------------------------------------


def append_market(sub_type: str, source: str, payload: dict[str, Any]) -> LedgerEvent:
    """Append a MARKET stream event.

    Typical sub_types: TICK, ORDERBOOK_SNAPSHOT, TRADE, OHLCV, FUNDING_RATE.

    Args:
        sub_type: canonical sub-type string (see event_types.MARKET_TYPES).
        source:   producing component, e.g. "INDIRA", "DATA_FEED".
        payload:  arbitrary dict; JSON-serialised before storage.

    Returns:
        The committed LedgerEvent with its event_id, sequence, and event_hash.
    """
    return get_event_store().append(_MARKET, sub_type, source, payload)


def append_system(sub_type: str, source: str, payload: dict[str, Any]) -> LedgerEvent:
    """Append a SYSTEM stream event.

    Typical sub_types: STARTUP, SHUTDOWN, MODE_TRANSITION, HEALTH_CHECK,
    CONFIG_RELOAD, MEMORY_HEALTH, SNAPSHOT_TAKEN.

    Args:
        sub_type: canonical sub-type string (see event_types.SYSTEM_TYPES).
        source:   producing component, e.g. "SYSTEM_ENGINE", "GOVERNANCE".
        payload:  arbitrary dict; JSON-serialised before storage.

    Returns:
        The committed LedgerEvent with its event_id, sequence, and event_hash.
    """
    return get_event_store().append(_SYSTEM, sub_type, source, payload)


def append_governance(sub_type: str, source: str, payload: dict[str, Any]) -> LedgerEvent:
    """Append a GOVERNANCE stream event.

    Typical sub_types: COGOV_*, OPGOV_*, SYSGOV_*, FINGOV_*,
    PATCH_*, LEARN_*, CONSENT_GRANTED, CONSENT_DENIED.

    Args:
        sub_type: canonical sub-type string (see event_types.GOVERNANCE_TYPES).
        source:   producing component, e.g. "GOVERNANCE_ENGINE", "COGOV_LAYER".
        payload:  arbitrary dict; JSON-serialised before storage.

    Returns:
        The committed LedgerEvent with its event_id, sequence, and event_hash.
    """
    return get_event_store().append(_GOVERNANCE, sub_type, source, payload)


def append_hazard(sub_type: str, source: str, payload: dict[str, Any]) -> LedgerEvent:
    """Append a HAZARD stream event.

    Typical sub_types: HAZ_01..HAZ_15, RUNTIME_PANIC, RUNTIME_TIMEOUT,
    RUNTIME_INTEGRITY_FAIL, RUNTIME_LOCKOUT.

    Args:
        sub_type: canonical sub-type string (see event_types.HAZARD_TYPES).
        source:   detecting component, e.g. "SYSTEM_ENGINE", "HAZARD_SENSOR".
        payload:  arbitrary dict; JSON-serialised before storage.

    Returns:
        The committed LedgerEvent with its event_id, sequence, and event_hash.
    """
    return get_event_store().append(_HAZARD, sub_type, source, payload)


def append_authority(sub_type: str, source: str, payload: dict[str, Any]) -> LedgerEvent:
    """Append an AUTHORITY stream event.

    Typical sub_types: MODE_LOCK, MODE_UNLOCK, STRATEGY_APPROVED,
    STRATEGY_SUSPENDED, OPERATOR_OVERRIDE, CONSENT_TOKEN_ISSUED.

    Args:
        sub_type: canonical sub-type string (see event_types.AUTHORITY_TYPES).
        source:   producing component, e.g. "GOVERNANCE_ENGINE", "OPERATOR_BRIDGE".
        payload:  arbitrary dict; JSON-serialised before storage.

    Returns:
        The committed LedgerEvent with its event_id, sequence, and event_hash.
    """
    return get_event_store().append(_AUTHORITY, sub_type, source, payload)


# ---------------------------------------------------------------------------
# AppendBatch — transactional multi-append context manager
# ---------------------------------------------------------------------------


class AppendBatch:
    """Buffer multiple appends and commit them atomically.

    SQLite WAL mode permits only one writer at a time; this context manager
    acquires the EventStore's internal lock for the duration of the batch so
    that no other writer can interleave. Events are written individually (each
    gets its own hash-chained row) but within a single BEGIN/COMMIT block,
    giving atomic visibility to readers that use isolation_level != None.

    Usage::

        with AppendBatch() as batch:
            batch.market("TICK", "INDIRA", {"bid": "100.0"})
            batch.system("HEALTH_CHECK", "SYSTEM_ENGINE", {"ok": "true"})

    If an exception is raised inside the block, the entire batch is rolled
    back and no events are persisted (partial writes are prevented).

    Note: AppendBatch is NOT re-entrant. Nesting two AppendBatch contexts
    will deadlock because both try to acquire the same EventStore lock.
    """

    def __init__(self) -> None:
        self._events: list[tuple[str, str, str, dict[str, Any]]] = []
        self._committed: list[LedgerEvent] = []
        self._active = False

    # ------------------------------------------------------------------ enter

    def __enter__(self) -> AppendBatch:
        self._active = True
        self._events.clear()
        self._committed.clear()
        return self

    # ------------------------------------------------------------------ helpers

    def market(self, sub_type: str, source: str, payload: dict[str, Any]) -> None:
        """Stage a MARKET event for batch commit."""
        self._check_active()
        self._events.append((_MARKET, sub_type, source, payload))

    def system(self, sub_type: str, source: str, payload: dict[str, Any]) -> None:
        """Stage a SYSTEM event for batch commit."""
        self._check_active()
        self._events.append((_SYSTEM, sub_type, source, payload))

    def governance(self, sub_type: str, source: str, payload: dict[str, Any]) -> None:
        """Stage a GOVERNANCE event for batch commit."""
        self._check_active()
        self._events.append((_GOVERNANCE, sub_type, source, payload))

    def hazard(self, sub_type: str, source: str, payload: dict[str, Any]) -> None:
        """Stage a HAZARD event for batch commit."""
        self._check_active()
        self._events.append((_HAZARD, sub_type, source, payload))

    def authority(self, sub_type: str, source: str, payload: dict[str, Any]) -> None:
        """Stage an AUTHORITY event for batch commit."""
        self._check_active()
        self._events.append((_AUTHORITY, sub_type, source, payload))

    def _check_active(self) -> None:
        if not self._active:
            raise RuntimeError(
                "AppendBatch: cannot stage events outside of a 'with' block. "
                "Use 'with AppendBatch() as batch: ...' syntax."
            )

    # ------------------------------------------------------------------ exit

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool:
        self._active = False
        if exc_type is not None:
            # Exception in caller block — discard staged events, do not write.
            self._events.clear()
            return False  # re-raise

        store = get_event_store()
        # Acquire the store lock for the entire batch so no other caller
        # can interleave hash-chain appends between our events.
        with store._lock:  # noqa: SLF001
            conn = store._conn  # noqa: SLF001
            conn.execute("BEGIN DEFERRED")
            try:
                for event_type, sub_type, source, payload in self._events:
                    ev = store.append(event_type, sub_type, source, payload)
                    self._committed.append(ev)
                conn.execute("COMMIT")
            except Exception:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                self._committed.clear()
                self._events.clear()
                raise

        self._events.clear()
        return False

    @property
    def committed(self) -> list[LedgerEvent]:
        """Return the list of events committed by the last batch (read-only view)."""
        return list(self._committed)


# ---------------------------------------------------------------------------
# Convenience context-manager alias
# ---------------------------------------------------------------------------


@contextmanager
def append_batch() -> Generator[AppendBatch, None, None]:
    """Functional alias for AppendBatch for callers who prefer 'with append_batch()'.

    Example::

        with append_batch() as batch:
            batch.market("TICK", "INDIRA", {"bid": "100.5"})
            batch.hazard("HAZ_01", "SENSOR", {"detail": "latency spike"})
    """
    batch = AppendBatch()
    with batch as b:
        yield b


__all__ = [
    "append_market",
    "append_system",
    "append_governance",
    "append_hazard",
    "append_authority",
    "AppendBatch",
    "append_batch",
]

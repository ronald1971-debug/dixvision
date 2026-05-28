"""
operator_governance/override_priority.py
DIX VISION v42.2 — Override Priority Manager

Manages the set of active operator overrides. Enforces the priority
hierarchy: KILL_SWITCH (5) > MODE_LOCK (4) > EXECUTION_HALT (3) >
PARAMETER_OVERRIDE (2) > SUGGESTION (1).

Invariant: a higher-priority override always supersedes a lower one.
Active overrides are indexed by (target, priority) so the same target
may carry multiple overrides at different priority tiers simultaneously.
"""

from __future__ import annotations

import threading
import time as _time
import uuid
from collections import defaultdict
from typing import Any

from core.contracts.operator_governance import (
    OverridePriority,
    OverrideRecord,
)
from state.ledger.event_store import append_event


class OverridePriorityManager:
    """
    Registry of active operator overrides.

    Thread-safe. Supports add, remove, and query of active overrides.
    Callers query effective_priority(target) to get the highest currently
    active override priority for a target subsystem.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # target → list[OverrideRecord]
        self._overrides: dict[str, list[OverrideRecord]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Override lifecycle
    # ------------------------------------------------------------------

    def add_override(
        self,
        priority: OverridePriority,
        issuer: str,
        target: str,
        payload: str,
        expires_ns: int = 0,
    ) -> OverrideRecord:
        """
        Register an active override.

        Returns the new OverrideRecord. Emits OPGOV_OVERRIDE_ADDED to the
        governance ledger.
        """
        override_id = str(uuid.uuid4())
        ts_ns = _time.time_ns()

        record = OverrideRecord(
            override_id=override_id,
            ts_ns=ts_ns,
            priority=priority,
            issuer=issuer,
            target=target,
            payload=payload,
            expires_ns=expires_ns,
        )

        with self._lock:
            self._overrides[target].append(record)

        append_event(
            "GOVERNANCE",
            "OPGOV_OVERRIDE_ADDED",
            "operator_governance.override_priority",
            {
                "override_id": override_id,
                "priority": priority.value,
                "ordinal": priority.ordinal(),
                "issuer": issuer,
                "target": target,
                "expires_ns": expires_ns,
            },
        )

        return record

    def remove_override(self, override_id: str) -> bool:
        """
        Remove an override by ID. Returns True if found and removed.
        """
        with self._lock:
            for target, records in self._overrides.items():
                for i, rec in enumerate(records):
                    if rec.override_id == override_id:
                        del records[i]
                        ts_ns = _time.time_ns()
                        break
                else:
                    continue
                break
            else:
                return False

        append_event(
            "GOVERNANCE",
            "OPGOV_OVERRIDE_REMOVED",
            "operator_governance.override_priority",
            {"override_id": override_id, "target": target},
        )
        return True

    def remove_all_for_target(self, target: str) -> int:
        """Remove all overrides for a target. Returns the count removed."""
        with self._lock:
            count = len(self._overrides.get(target, []))
            self._overrides[target] = []
        if count:
            append_event(
                "GOVERNANCE",
                "OPGOV_OVERRIDES_CLEARED",
                "operator_governance.override_priority",
                {"target": target, "count": count},
            )
        return count

    # ------------------------------------------------------------------
    # Expiry sweep
    # ------------------------------------------------------------------

    def expire_stale(self) -> int:
        """
        Remove overrides whose expires_ns has passed. Returns count removed.

        Overrides with expires_ns == 0 are permanent until explicitly removed.
        """
        now_ns = _time.time_ns()
        removed = 0

        with self._lock:
            for target in list(self._overrides.keys()):
                before = len(self._overrides[target])
                self._overrides[target] = [
                    r for r in self._overrides[target]
                    if r.expires_ns == 0 or r.expires_ns > now_ns
                ]
                removed += before - len(self._overrides[target])

        return removed

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def effective_priority(self, target: str) -> OverridePriority | None:
        """
        Return the highest-priority active override for a target, or None.
        """
        self.expire_stale()
        with self._lock:
            records = self._overrides.get(target, [])
            if not records:
                return None
            return max(records, key=lambda r: r.priority.ordinal()).priority

    def active_overrides(self, target: str | None = None) -> list[OverrideRecord]:
        """
        Return active overrides, optionally filtered by target.
        """
        self.expire_stale()
        with self._lock:
            if target is not None:
                return list(self._overrides.get(target, []))
            return [r for records in self._overrides.values() for r in records]

    def override_count(self) -> int:
        """Total count of active overrides across all targets."""
        self.expire_stale()
        with self._lock:
            return sum(len(v) for v in self._overrides.values())

    def snapshot(self) -> dict[str, Any]:
        self.expire_stale()
        with self._lock:
            return {
                "active_count": sum(len(v) for v in self._overrides.values()),
                "targets": {
                    t: [
                        {
                            "override_id": r.override_id,
                            "priority": r.priority.value,
                            "issuer": r.issuer,
                            "expires_ns": r.expires_ns,
                        }
                        for r in recs
                    ]
                    for t, recs in self._overrides.items()
                    if recs
                },
            }


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: OverridePriorityManager | None = None
_lock = threading.Lock()


def get_override_priority_manager() -> OverridePriorityManager:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = OverridePriorityManager()
    return _instance


__all__ = ["OverridePriorityManager", "get_override_priority_manager"]

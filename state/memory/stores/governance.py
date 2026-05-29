"""state.memory.stores.governance — GovernanceMemoryStore.

Records mode transitions, operator overrides, governance violations,
and policy enforcement events. The operator can audit every governance
decision that shaped the system's behavior.

Feeds CognitionTimeline with GOVERNANCE-kind records.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from types import MappingProxyType
from typing import Any

from state.memory.contracts import MemoryKind, MemoryRecord

_logger   = logging.getLogger(__name__)
_MAX_SIZE = 2_000


class GovernanceMemoryStore:
    """Auditable log of all governance events."""

    def __init__(self, max_size: int = _MAX_SIZE) -> None:
        self._max_size  = max_size
        self._lock      = threading.Lock()
        self._records:  deque[MemoryRecord] = deque(maxlen=max_size)
        self._violations_by_type: dict[str, int] = {}
        self._mode_history:       list[tuple[int, str]] = []  # (ts_ns, mode)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record_mode_transition(
        self,
        *,
        record_id: str,
        from_mode: str,
        to_mode:   str,
        ts_ns:     int,
        reason:    str,
        source:    str = "governance_router",
        tags:      frozenset[str] = frozenset(),
    ) -> MemoryRecord:
        rec = MemoryRecord(
            record_id = record_id,
            kind      = MemoryKind.GOVERNANCE,
            ts_ns     = ts_ns,
            source    = source,
            summary   = f"MODE {from_mode} → {to_mode}: {reason}",
            body      = MappingProxyType({
                "from_mode": from_mode,
                "to_mode":   to_mode,
                "reason":    reason,
                "event":     "mode_transition",
            }),
            tags      = tags | frozenset(["mode_transition", from_mode.lower(), to_mode.lower()]),
        )
        with self._lock:
            self._records.append(rec)
            self._mode_history.append((ts_ns, to_mode))
        return rec

    def record_violation(
        self,
        *,
        record_id:      str,
        violation_type: str,
        severity:       str,
        ts_ns:          int,
        description:    str,
        source:         str = "cognitive_governance",
        tags:           frozenset[str] = frozenset(),
    ) -> MemoryRecord:
        rec = MemoryRecord(
            record_id  = record_id,
            kind       = MemoryKind.GOVERNANCE,
            ts_ns      = ts_ns,
            source     = source,
            summary    = f"VIOLATION [{severity}] {violation_type}: {description}",
            body       = MappingProxyType({
                "violation_type": violation_type,
                "severity":       severity,
                "description":    description,
                "event":          "violation",
            }),
            tags       = tags | frozenset(["violation", violation_type.lower(), severity.lower()]),
            confidence = 1.0 if severity == "CRITICAL" else 0.5,
        )
        with self._lock:
            self._records.append(rec)
            self._violations_by_type[violation_type] = (
                self._violations_by_type.get(violation_type, 0) + 1
            )
        return rec

    def record_operator_action(
        self,
        *,
        record_id: str,
        action:    str,
        ts_ns:     int,
        detail:    str,
        source:    str = "operator",
        tags:      frozenset[str] = frozenset(),
    ) -> MemoryRecord:
        rec = MemoryRecord(
            record_id = record_id,
            kind      = MemoryKind.GOVERNANCE,
            ts_ns     = ts_ns,
            source    = source,
            summary   = f"OPERATOR {action}: {detail}",
            body      = MappingProxyType({"action": action, "detail": detail, "event": "operator_action"}),
            tags      = tags | frozenset(["operator_action", action.lower()]),
        )
        with self._lock:
            self._records.append(rec)
        return rec

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def current_mode(self) -> str | None:
        with self._lock:
            return self._mode_history[-1][1] if self._mode_history else None

    def violation_counts(self) -> dict[str, int]:
        with self._lock:
            return dict(self._violations_by_type)

    def mode_history(self, limit: int = 20) -> list[dict]:
        with self._lock:
            hist = list(self._mode_history[-limit:])
        return [{"ts_ns": ts, "mode": m} for ts, m in reversed(hist)]

    def recent(self, limit: int = 20) -> list[MemoryRecord]:
        with self._lock:
            recs = list(self._records)
        recs.sort(key=lambda r: r.ts_ns, reverse=True)
        return recs[:limit]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            total_violations = sum(self._violations_by_type.values())
            return {
                "active":           True,
                "size":             len(self._records),
                "max_size":         self._max_size,
                "current_mode":     self._mode_history[-1][1] if self._mode_history else None,
                "mode_transitions": len(self._mode_history),
                "total_violations": total_violations,
                "violations_by_type": dict(self._violations_by_type),
            }


_singleton: GovernanceMemoryStore | None = None
_lock = threading.Lock()


def get_governance_memory_store() -> GovernanceMemoryStore:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = GovernanceMemoryStore()
    return _singleton


__all__ = ["GovernanceMemoryStore", "get_governance_memory_store"]

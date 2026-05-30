"""governance_engine.hardening.isolation_boundary — Runtime isolation boundary.

Tracks cross-engine call observations and verifies them against the system
authority matrix.  Any engine-to-engine path that bypasses the defined
authority chain is a boundary violation and triggers a CRITICAL hazard.

Authority matrix (allowed directed edges):
  data_feed          → intelligence_engine
  intelligence_engine → governance_engine
  governance_engine  → execution_engine
  execution_engine   → venue

Bidirectional reads back up the chain (responses) are modelled as the
reverse of the same edge and are allowed.  Everything else is a violation.

Usage:
  boundary = get_isolation_boundary()
  boundary.observe("intelligence_engine", "governance_engine", ts_ns)  # OK
  boundary.observe("intelligence_engine", "execution_engine", ts_ns)   # VIOLATION

Authority (L1): stdlib only at module level.
INV-15: ts_ns is caller-supplied.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Authority matrix — single source of truth
# ---------------------------------------------------------------------------

AUTHORITY_EDGES: frozenset[tuple[str, str]] = frozenset({
    ("data_feed",           "intelligence_engine"),
    ("intelligence_engine", "governance_engine"),
    ("governance_engine",   "execution_engine"),
    ("execution_engine",    "venue"),
    # Reverse (response path) also allowed
    ("intelligence_engine", "data_feed"),
    ("governance_engine",   "intelligence_engine"),
    ("execution_engine",    "governance_engine"),
    ("venue",               "execution_engine"),
})

KNOWN_ENGINES: frozenset[str] = frozenset({
    "data_feed", "intelligence_engine", "governance_engine",
    "execution_engine", "venue",
})


@dataclass(frozen=True, slots=True)
class BoundaryViolation:
    """Record of a single boundary violation."""

    caller: str
    callee: str
    ts_ns: int
    detail: str


@dataclass
class BoundaryObservation:
    """Mutable observation counter for a (caller, callee) pair."""

    caller: str
    callee: str
    allowed: bool
    count: int = 0
    last_ts_ns: int = 0


class RuntimeIsolationBoundary:
    """Observes cross-engine calls and enforces the authority matrix.

    Args:
        strict_unknown: if True, calls involving unknown engine names are
            treated as violations (default True — fail closed).
    """

    def __init__(self, *, strict_unknown: bool = True) -> None:
        self._lock = threading.Lock()
        self._strict_unknown = strict_unknown
        self._observations: dict[tuple[str, str], BoundaryObservation] = {}
        self._violations: list[BoundaryViolation] = []
        self._violation_count: int = 0
        self._allow_count: int = 0

    # ------------------------------------------------------------------
    # Observe
    # ------------------------------------------------------------------

    def observe(self, caller: str, callee: str, ts_ns: int) -> bool:
        """Record a cross-engine call observation.

        Returns True if the call is within authority, False on violation.
        Violations are appended to the violation log and hazards are emitted.
        """
        allowed = self._is_allowed(caller, callee)
        key = (caller, callee)

        with self._lock:
            if key not in self._observations:
                self._observations[key] = BoundaryObservation(
                    caller=caller, callee=callee, allowed=allowed
                )
            obs = self._observations[key]
            obs.count += 1
            obs.last_ts_ns = ts_ns

            if allowed:
                self._allow_count += 1
            else:
                self._violation_count += 1
                violation = BoundaryViolation(
                    caller=caller,
                    callee=callee,
                    ts_ns=ts_ns,
                    detail=(
                        f"boundary violation: {caller!r} → {callee!r} "
                        f"not in authority matrix"
                    ),
                )
                self._violations.append(violation)
                if len(self._violations) > 1000:
                    self._violations = self._violations[-500:]

        if not allowed:
            self._emit_violation(caller, callee, ts_ns)
            _logger.critical(
                "IsolationBoundary: VIOLATION %s → %s", caller, callee
            )
        return allowed

    def is_allowed(self, caller: str, callee: str) -> bool:
        """Check whether a cross-engine call is within authority (no side effects)."""
        return self._is_allowed(caller, callee)

    # ------------------------------------------------------------------
    # Read surface
    # ------------------------------------------------------------------

    def violations(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            recent = self._violations[-limit:]
        return [
            {"caller": v.caller, "callee": v.callee, "ts_ns": v.ts_ns, "detail": v.detail}
            for v in recent
        ]

    def observation_matrix(self) -> list[dict[str, Any]]:
        with self._lock:
            obs = list(self._observations.values())
        return [
            {
                "caller": o.caller,
                "callee": o.callee,
                "allowed": o.allowed,
                "count": o.count,
                "last_ts_ns": o.last_ts_ns,
            }
            for o in obs
        ]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            v_count = self._violation_count
            a_count = self._allow_count
            recent_violations = [
                {"caller": v.caller, "callee": v.callee, "ts_ns": v.ts_ns}
                for v in self._violations[-10:]
            ]
        return {
            "allow_count": a_count,
            "violation_count": v_count,
            "authority_edges": [list(e) for e in sorted(AUTHORITY_EDGES)],
            "recent_violations": recent_violations,
            "observation_count": len(self._observations),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _is_allowed(self, caller: str, callee: str) -> bool:
        if caller == callee:
            return True  # intra-engine calls are always fine
        unknown = (caller not in KNOWN_ENGINES) or (callee not in KNOWN_ENGINES)
        if unknown:
            return not self._strict_unknown
        return (caller, callee) in AUTHORITY_EDGES

    @staticmethod
    def _emit_violation(caller: str, callee: str, ts_ns: int) -> None:
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().publish(CognitiveChannel.DYON_VIOLATION, {
                "source": "isolation_boundary",
                "hazard": "BOUNDARY_VIOLATION",
                "caller": caller,
                "callee": callee,
                "severity": "CRITICAL",
                "ts_ns": ts_ns,
            })
        except Exception:
            pass
        try:
            from state.ledger.append import append_event
            append_event(
                stream="GOVERNANCE",
                kind="BOUNDARY_VIOLATION",
                source="governance_engine",
                payload={
                    "caller": caller,
                    "callee": callee,
                    "ts_ns": ts_ns,
                    "severity": "CRITICAL",
                },
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_boundary: RuntimeIsolationBoundary | None = None
_boundary_lock = threading.Lock()


def get_isolation_boundary(
    *, strict_unknown: bool = True
) -> RuntimeIsolationBoundary:
    global _boundary
    with _boundary_lock:
        if _boundary is None:
            _boundary = RuntimeIsolationBoundary(strict_unknown=strict_unknown)
    return _boundary


__all__ = [
    "AUTHORITY_EDGES",
    "BoundaryObservation",
    "BoundaryViolation",
    "KNOWN_ENGINES",
    "RuntimeIsolationBoundary",
    "get_isolation_boundary",
]

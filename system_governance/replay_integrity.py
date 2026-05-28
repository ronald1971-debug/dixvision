"""
system_governance/replay_integrity.py
DIX VISION v42.2 — Replay Integrity Guard

Invariant INV-15: events must be deterministically replayable. Any
element in the event payload that introduces non-determinism
(wall-clock timestamps, random values, I/O results outside the event
itself) must be declared and isolated so replay consumers can replace
them with deterministic equivalents.

This guard validates replay packs:
  - Detects undeclared non-deterministic elements
  - Hashes the deterministic portion of each event for integrity verification
  - Records replay validation results for auditability
"""

from __future__ import annotations

import hashlib
import json
import threading
import time as _time
from collections import deque
from typing import Any

from core.contracts.system_governance import ReplayIntegrityResult
from state.ledger.event_store import append_event


_MAX_HISTORY = 1_000

# Elements that are intrinsically non-deterministic and must be declared
_KNOWN_NON_DETERMINISTIC = frozenset(
    {
        "wall_ns",
        "ts_wall",
        "random_seed",
        "random_value",
        "nonce",
        "uuid",
        "request_id",
    }
)


class ReplayIntegrityGuard:
    """
    Validates deterministic replay integrity for events (INV-15).

    Thread-safe. Each call to validate_event() checks a single event
    payload for undeclared non-deterministic elements and computes a
    replay hash over the deterministic portion.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._results: deque[ReplayIntegrityResult] = deque(maxlen=_MAX_HISTORY)
        self._violation_count: int = 0

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_event(
        self,
        event_id: str,
        payload: dict[str, Any],
        declared_non_deterministic: tuple[str, ...] = (),
    ) -> ReplayIntegrityResult:
        """
        Validate replay determinism for a single event payload.

        declared_non_deterministic: keys in payload that the emitter
        explicitly declares as non-deterministic. Any other keys from
        _KNOWN_NON_DETERMINISTIC found in the payload without being
        declared are flagged as violations.

        Returns a ReplayIntegrityResult. All non-determinism violations
        are emitted to the ledger.
        """
        ts_ns = _time.time_ns()
        declared_set = set(declared_non_deterministic)

        # Detect undeclared non-deterministic elements
        undeclared = tuple(
            key
            for key in payload
            if key in _KNOWN_NON_DETERMINISTIC and key not in declared_set
        )

        # Compute replay hash over deterministic keys only
        det_keys = {
            k: v
            for k, v in payload.items()
            if k not in _KNOWN_NON_DETERMINISTIC and k not in declared_set
        }
        try:
            canonical = json.dumps(det_keys, sort_keys=True, default=str)
            replay_hash = hashlib.sha256(canonical.encode()).hexdigest()[:16]
        except Exception:
            replay_hash = ""

        deterministic = len(undeclared) == 0

        result = ReplayIntegrityResult(
            ts_ns=ts_ns,
            event_id=event_id,
            deterministic=deterministic,
            non_deterministic_elements=undeclared,
            replay_hash=replay_hash,
            detail=(
                "OK"
                if deterministic
                else f"undeclared non-deterministic elements: {list(undeclared)}"
            ),
        )

        with self._lock:
            self._results.append(result)
            if not deterministic:
                self._violation_count += 1

        if not deterministic:
            append_event(
                "GOVERNANCE",
                "SYSGOV_REPLAY_INTEGRITY_VIOLATION",
                "system_governance.replay_integrity",
                {
                    "event_id": event_id,
                    "undeclared_non_deterministic": list(undeclared),
                    "replay_hash": replay_hash,
                    "detail": result.detail,
                },
            )

        return result

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def violation_count(self) -> int:
        with self._lock:
            return self._violation_count

    def recent_results(self, n: int = 20) -> list[ReplayIntegrityResult]:
        with self._lock:
            items = list(self._results)
        return items[-n:]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "violation_count": self._violation_count,
                "history_size": len(self._results),
            }


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: ReplayIntegrityGuard | None = None
_lock = threading.Lock()


def get_replay_integrity_guard() -> ReplayIntegrityGuard:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = ReplayIntegrityGuard()
    return _instance


__all__ = ["ReplayIntegrityGuard", "get_replay_integrity_guard"]

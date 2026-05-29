"""DyonMemory — persistent self-improvement memory for DYON (P2 Autonomous Loop).

DYON's memory of what it has seen, proposed, and learned.  Without this,
every scan is independent: DYON has no awareness that a violation has been
present for 40 scans, or that its patch for INV-15 in module X was previously
rejected.

Tracks:
    violation_counts     — how many scans each violation has appeared in
    violation_first_seen — when DYON first detected each violation
    violation_last_seen  — when DYON last saw each violation
    patch_outcomes       — what happened to each generated PatchInstruction
    persistent_violations — violations seen ≥ threshold (structural, not transient)

Persistence:
    Durable state stored in CognitionPersistenceStore (episodes table,
    store_kind='dyon_memory').  Reloaded on construction so DYON remembers
    across restarts.

Authority (L2/B1): imports only from evolution_engine.* and core.*.
INV-15: ts_ns is caller-supplied.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from typing import Any

_logger = logging.getLogger(__name__)

_STORE_KIND = "dyon_memory"
_RECURRENCE_THRESHOLD = 3     # how many scans before flagged as structural


# ---------------------------------------------------------------------------
# Memory records
# ---------------------------------------------------------------------------


@dataclass
class ViolationRecord:
    """What DYON knows about one recurring violation."""

    violation_key: str          # "{invariant_id}:{source_module}"
    invariant_id: str
    source_module: str
    imported_module: str
    count: int = 0
    first_seen_ns: int = 0
    last_seen_ns: int = 0
    last_severity: str = "WARNING"


@dataclass
class PatchOutcomeRecord:
    """What happened to one of DYON's patch instructions."""

    patch_id: str
    violation_key: str
    outcome: str                # "PROPOSED" | "APPROVED" | "REJECTED" | "APPLIED"
    ts_ns: int
    notes: str = ""


# ---------------------------------------------------------------------------
# DyonMemory
# ---------------------------------------------------------------------------


class DyonMemory:
    """DYON's persistent engineering memory.

    Keeps track of which violations are structural (recurring) vs transient,
    and learns from patch outcome history to prioritize future proposals.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._violations: dict[str, ViolationRecord] = {}
        self._patch_outcomes: dict[str, PatchOutcomeRecord] = {}
        self._save_seq: int = 0
        self._restore()

    # ------------------------------------------------------------------
    # Violation memory
    # ------------------------------------------------------------------

    def remember_violation(
        self,
        *,
        invariant_id: str,
        source_module: str,
        imported_module: str,
        severity: str,
        ts_ns: int,
    ) -> ViolationRecord:
        """Record one violation observation.  Returns the updated record."""
        key = f"{invariant_id}:{source_module}"
        with self._lock:
            rec = self._violations.get(key)
            if rec is None:
                rec = ViolationRecord(
                    violation_key=key,
                    invariant_id=invariant_id,
                    source_module=source_module,
                    imported_module=imported_module,
                    first_seen_ns=ts_ns,
                    last_seen_ns=ts_ns,
                    count=1,
                    last_severity=severity,
                )
            else:
                rec.count += 1
                rec.last_seen_ns = ts_ns
                rec.last_severity = severity
            self._violations[key] = rec
        return rec

    def recurrence_count(self, invariant_id: str, source_module: str) -> int:
        key = f"{invariant_id}:{source_module}"
        with self._lock:
            return self._violations.get(key, ViolationRecord("", "", "", "")).count

    def persistent_violations(self) -> list[ViolationRecord]:
        """Return violations seen at least RECURRENCE_THRESHOLD times."""
        with self._lock:
            return [
                r for r in self._violations.values()
                if r.count >= _RECURRENCE_THRESHOLD
            ]

    def is_known(self, invariant_id: str, source_module: str) -> bool:
        """Whether DYON has seen this violation before."""
        key = f"{invariant_id}:{source_module}"
        with self._lock:
            return key in self._violations

    # ------------------------------------------------------------------
    # Patch outcome memory
    # ------------------------------------------------------------------

    def record_patch_outcome(
        self,
        *,
        patch_id: str,
        violation_key: str,
        outcome: str,
        ts_ns: int,
        notes: str = "",
    ) -> None:
        """Persist what happened to a patch proposal."""
        with self._lock:
            self._patch_outcomes[patch_id] = PatchOutcomeRecord(
                patch_id=patch_id,
                violation_key=violation_key,
                outcome=outcome,
                ts_ns=ts_ns,
                notes=notes,
            )
        self._persist_outcome(patch_id)

    def patch_outcome(self, patch_id: str) -> str | None:
        """Return the outcome for *patch_id*, or None if not recorded."""
        with self._lock:
            rec = self._patch_outcomes.get(patch_id)
            return rec.outcome if rec else None

    def rejection_count(self, violation_key: str) -> int:
        """How many patches for *violation_key* were rejected."""
        with self._lock:
            return sum(
                1 for r in self._patch_outcomes.values()
                if r.violation_key == violation_key and r.outcome == "REJECTED"
            )

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self, top_n: int = 20) -> dict[str, Any]:
        with self._lock:
            persistent = [
                {
                    "key": r.violation_key,
                    "count": r.count,
                    "severity": r.last_severity,
                    "first_seen_ns": r.first_seen_ns,
                }
                for r in sorted(
                    self._violations.values(),
                    key=lambda r: -r.count,
                )[:top_n]
            ]
        return {
            "total_violation_keys": len(self._violations),
            "persistent_violation_count": len(self.persistent_violations()),
            "patch_outcomes_recorded": len(self._patch_outcomes),
            "top_persistent": persistent,
        }

    # ------------------------------------------------------------------
    # Periodic persistence (save after every scan batch)
    # ------------------------------------------------------------------

    def persist(self, ts_ns: int) -> None:
        """Flush current violation memory to SQLite. Best-effort."""
        self._save_seq += 1
        try:
            from state.cognition_persistence import get_cognition_persistence_store
            ps = get_cognition_persistence_store()
            with self._lock:
                blobs = {k: self._violation_to_dict(r) for k, r in self._violations.items()}
            ps.save_episode(
                store_kind=_STORE_KIND,
                episode_id=f"dyon_violations_snapshot_{self._save_seq}",
                ts_ns=ts_ns,
                data={"violations": blobs, "save_seq": self._save_seq},
            )
        except Exception as exc:
            _logger.debug("DyonMemory.persist error: %s", exc)

    def _restore(self) -> None:
        """Load the most recent violation snapshot from SQLite."""
        try:
            from state.cognition_persistence import get_cognition_persistence_store
            rows = get_cognition_persistence_store().load_episodes(
                _STORE_KIND, limit=1
            )
            if not rows:
                return
            blobs = rows[0].get("violations", {})
            for key, d in blobs.items():
                try:
                    self._violations[key] = ViolationRecord(
                        violation_key=key,
                        invariant_id=d.get("invariant_id", ""),
                        source_module=d.get("source_module", ""),
                        imported_module=d.get("imported_module", ""),
                        count=int(d.get("count", 0)),
                        first_seen_ns=int(d.get("first_seen_ns", 0)),
                        last_seen_ns=int(d.get("last_seen_ns", 0)),
                        last_severity=d.get("last_severity", "WARNING"),
                    )
                except Exception:
                    pass
            if self._violations:
                _logger.info(
                    "DyonMemory: restored %d violation records from persistence",
                    len(self._violations),
                )
        except Exception as exc:
            _logger.debug("DyonMemory._restore error: %s", exc)

    def _persist_outcome(self, patch_id: str) -> None:
        try:
            from state.cognition_persistence import get_cognition_persistence_store
            with self._lock:
                rec = self._patch_outcomes.get(patch_id)
            if rec is None:
                return
            get_cognition_persistence_store().save_episode(
                store_kind="dyon_patch_outcome",
                episode_id=patch_id,
                ts_ns=rec.ts_ns,
                data={
                    "violation_key": rec.violation_key,
                    "outcome": rec.outcome,
                    "notes": rec.notes,
                },
            )
        except Exception:
            pass

    @staticmethod
    def _violation_to_dict(r: ViolationRecord) -> dict[str, Any]:
        return {
            "invariant_id": r.invariant_id,
            "source_module": r.source_module,
            "imported_module": r.imported_module,
            "count": r.count,
            "first_seen_ns": r.first_seen_ns,
            "last_seen_ns": r.last_seen_ns,
            "last_severity": r.last_severity,
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_memory: DyonMemory | None = None
_memory_lock = threading.Lock()


def get_dyon_memory() -> DyonMemory:
    """Return the process-wide DyonMemory singleton."""
    global _memory
    with _memory_lock:
        if _memory is None:
            _memory = DyonMemory()
    return _memory


__all__ = [
    "DyonMemory",
    "PatchOutcomeRecord",
    "ViolationRecord",
    "get_dyon_memory",
]

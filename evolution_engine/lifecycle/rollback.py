"""evolution_engine.lifecycle.rollback — Stage 7: rollback engine with snapshot registry.

RollbackEngine:
  - Maintains an in-memory snapshot registry keyed by proposal_id.
  - register_for_rollback() is called at the PROMOTED stage to save the
    pre-promotion snapshot so it can be restored later.
  - execute_rollback() restores the snapshot and emits a RollbackRecord.

Snapshots contain the strategy registry state at promotion time.  When the
strategy registry is unavailable, the snapshot is recorded as a tombstone
and rollback logs the intent without a live registry restore.

Authority (L2/B1): stdlib only at module level.
INV-15: ts_ns is caller-supplied.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from evolution_engine.lifecycle.contracts import ProposalRecord, RollbackRecord

_logger = logging.getLogger(__name__)


class RollbackEngine:
    """Manages pre-promotion snapshots and executes governed rollbacks.

    Args:
        max_snapshots: rolling limit on stored snapshots.
    """

    def __init__(self, *, max_snapshots: int = 100) -> None:
        self._lock = threading.Lock()
        self._max_snapshots = max_snapshots
        # proposal_id → {snapshot_key, payload}
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._rollback_count: int = 0

    # ------------------------------------------------------------------
    # Registration (called at PROMOTED stage)
    # ------------------------------------------------------------------

    def register_for_rollback(self, record: "ProposalRecord", ts_ns: int) -> str:
        """Save a pre-promotion snapshot for *record*.

        Returns the snapshot_key that can be passed to execute_rollback().
        """
        import hashlib
        snapshot_key = hashlib.blake2b(
            f"{record.proposal_id}:{ts_ns}".encode(), digest_size=8
        ).hexdigest()
        payload = self._capture_registry_state(record.proposal_id, ts_ns)
        with self._lock:
            self._snapshots[record.proposal_id] = {
                "snapshot_key": snapshot_key,
                "payload": payload,
                "ts_ns": ts_ns,
            }
            # Evict oldest if over limit
            if len(self._snapshots) > self._max_snapshots:
                oldest = next(iter(self._snapshots))
                del self._snapshots[oldest]
        _logger.debug(
            "RollbackEngine: registered snapshot %s for %s",
            snapshot_key,
            record.proposal_id[:16],
        )
        return snapshot_key

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute_rollback(
        self,
        record: "ProposalRecord",
        trigger: str,
        operator_id: str,
        reason: str,
        ts_ns: int,
    ) -> "RollbackRecord":
        """Execute rollback for *record* and return a RollbackRecord.

        Never raises.
        """
        from evolution_engine.lifecycle.contracts import RollbackRecord

        with self._lock:
            snap = self._snapshots.pop(record.proposal_id, None)
            self._rollback_count += 1

        if snap is None:
            snapshot_key = f"tombstone_{record.proposal_id[:8]}"
            _logger.warning(
                "RollbackEngine: no snapshot for %s — tombstone rollback",
                record.proposal_id[:16],
            )
        else:
            snapshot_key = snap["snapshot_key"]
            self._restore_registry_state(snap["payload"], record.proposal_id, ts_ns)

        rollback_record = RollbackRecord(
            snapshot_key=snapshot_key,
            trigger=trigger,
            operator_id=operator_id,
            reason=reason,
            ts_ns=ts_ns,
        )
        self._emit_rollback_event(record, rollback_record)
        return rollback_record

    def has_snapshot(self, proposal_id: str) -> bool:
        with self._lock:
            return proposal_id in self._snapshots

    @property
    def rollback_count(self) -> int:
        return self._rollback_count

    @property
    def snapshot_count(self) -> int:
        with self._lock:
            return len(self._snapshots)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _capture_registry_state(proposal_id: str, ts_ns: int) -> dict[str, Any]:
        """Capture current strategy registry state (best-effort)."""
        try:
            import importlib
            mod = importlib.import_module("governance_engine.strategy_registry")
            reg = mod.get_strategy_registry()
            if hasattr(reg, "snapshot"):
                return {"registry": reg.snapshot(), "proposal_id": proposal_id, "ts_ns": ts_ns}
        except Exception:
            pass
        return {"registry": None, "proposal_id": proposal_id, "ts_ns": ts_ns}

    @staticmethod
    def _restore_registry_state(payload: dict[str, Any], proposal_id: str, ts_ns: int) -> None:
        """Restore strategy registry to pre-promotion state (best-effort)."""
        try:
            reg_snap = payload.get("registry")
            if reg_snap is None:
                return
            import importlib
            mod = importlib.import_module("governance_engine.strategy_registry")
            reg = mod.get_strategy_registry()
            if hasattr(reg, "rollback"):
                reg.rollback(proposal_id, ts_ns=ts_ns)
        except Exception as exc:
            _logger.debug("RollbackEngine: registry restore error: %s", exc)

    @staticmethod
    def _emit_rollback_event(
        record: "ProposalRecord", rr: "RollbackRecord"
    ) -> None:
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().publish(CognitiveChannel.DYON_PROPOSAL, {
                "proposal_id": record.proposal_id,
                "pipeline_stage": "ROLLED_BACK",
                "trigger": rr.trigger,
                "operator_id": rr.operator_id,
                "snapshot_key": rr.snapshot_key,
                "ts_ns": rr.ts_ns,
            })
        except Exception:
            pass
        try:
            from state.ledger.append import append_event
            append_event(
                stream="SYSTEM",
                kind="EVOLUTION_ROLLBACK",
                source="DYON",
                payload={
                    "proposal_id": record.proposal_id,
                    "snapshot_key": rr.snapshot_key,
                    "trigger": rr.trigger,
                    "operator_id": rr.operator_id,
                    "reason": rr.reason,
                    "ts_ns": rr.ts_ns,
                },
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_engine: RollbackEngine | None = None
_engine_lock = threading.Lock()


def get_rollback_engine(*, max_snapshots: int = 100) -> RollbackEngine:
    """Return the process-wide RollbackEngine singleton."""
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = RollbackEngine(max_snapshots=max_snapshots)
    return _engine


__all__ = ["RollbackEngine", "get_rollback_engine"]

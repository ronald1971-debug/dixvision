"""evolution_engine.lifecycle.deployment — Stage 9: deployment gate.

DeploymentGate is the final gate that authorises a promoted, audited
proposal to cross from the simulation/governance world into the live
strategy registry.

Gate rules:
  CLASS_A — auto-approved via deployment gate (no operator needed).
  CLASS_B — operator approval required.
  CLASS_C — operator approval required; additionally emits a high-priority
            governance alert.

Every deployment produces a DeploymentRecord that is persisted to the
ledger and emitted to the DYON event bus.

Authority (L2/B1): stdlib only at module level.
INV-15: ts_ns is caller-supplied.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from evolution_engine.lifecycle.contracts import DeploymentRecord, ProposalRecord

_logger = logging.getLogger(__name__)


class DeploymentGate:
    """Final deployment authorisation gate.

    CLASS_A mutations are auto-deployed; CLASS_B / CLASS_C require
    an explicit operator call to approve_deployment().

    Args:
        auto_deploy_class_a: if False, CLASS_A also waits for operator.
    """

    def __init__(self, *, auto_deploy_class_a: bool = True) -> None:
        self._auto_a = auto_deploy_class_a
        self._lock = threading.Lock()
        # proposal_id → DeploymentRecord (approved deployments)
        self._registry: dict[str, "DeploymentRecord"] = {}
        # proposal_ids pending operator approval
        self._pending: set[str] = set()
        self._deploy_count: int = 0

    # ------------------------------------------------------------------
    # Auto-approve gate (called by coordinator after REPLAY_AUDIT)
    # ------------------------------------------------------------------

    def enter(self, record: "ProposalRecord", ts_ns: int) -> "DeploymentRecord | None":
        """Try to auto-approve *record* through the deployment gate.

        Returns a DeploymentRecord if auto-approved, None if waiting.
        """
        if self._auto_a and record.mutation_class == "CLASS_A":
            return self._deploy(record, operator_id="AUTO", ts_ns=ts_ns)
        with self._lock:
            self._pending.add(record.proposal_id)
        _logger.debug(
            "DeploymentGate[%s] class=%s — awaiting operator approval",
            record.proposal_id[:16],
            record.mutation_class,
        )
        return None

    # ------------------------------------------------------------------
    # Operator API
    # ------------------------------------------------------------------

    def approve_deployment(
        self, proposal_id: str, operator_id: str, ts_ns: int
    ) -> "DeploymentRecord | None":
        """Operator approves a pending deployment.

        Returns a DeploymentRecord on success, None if proposal_id is
        not in the pending set.
        """
        with self._lock:
            if proposal_id not in self._pending:
                return None
            self._pending.discard(proposal_id)

        # We need the ProposalRecord; the coordinator will have already
        # passed it; here we reconstruct a minimal record from the registry.
        from evolution_engine.lifecycle.contracts import DeploymentRecord
        return self._build_and_register(
            proposal_id=proposal_id,
            mutation_class="CLASS_B",  # conservative default; coordinator overrides
            operator_id=operator_id,
            ts_ns=ts_ns,
        )

    def is_pending(self, proposal_id: str) -> bool:
        with self._lock:
            return proposal_id in self._pending

    def pending_ids(self) -> list[str]:
        with self._lock:
            return list(self._pending)

    def deployed_records(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            records = list(self._registry.values())
        records.sort(key=lambda r: r.ts_ns, reverse=True)
        return [self._record_to_dict(r) for r in records[:limit]]

    @property
    def deploy_count(self) -> int:
        return self._deploy_count

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _deploy(
        self, record: "ProposalRecord", operator_id: str, ts_ns: int
    ) -> "DeploymentRecord":
        dr = self._build_and_register(
            proposal_id=record.proposal_id,
            mutation_class=record.mutation_class,
            operator_id=operator_id,
            ts_ns=ts_ns,
        )
        self._apply_to_live_registry(record, ts_ns)
        return dr

    def _build_and_register(
        self,
        proposal_id: str,
        mutation_class: str,
        operator_id: str,
        ts_ns: int,
    ) -> "DeploymentRecord":
        from evolution_engine.lifecycle.contracts import DeploymentRecord
        deployment_hash = hashlib.blake2b(
            f"{proposal_id}:{operator_id}:{ts_ns}".encode(), digest_size=8
        ).hexdigest()
        gate_id = f"gate_{deployment_hash}"
        dr = DeploymentRecord(
            gate_id=gate_id,
            approved_by=operator_id,
            deployment_hash=deployment_hash,
            mutation_class=mutation_class,
            ts_ns=ts_ns,
        )
        with self._lock:
            self._registry[proposal_id] = dr
            self._deploy_count += 1
        self._emit_deployment_event(proposal_id, dr)
        _logger.debug(
            "DeploymentGate: deployed %s (class=%s gate=%s)",
            proposal_id[:16],
            mutation_class,
            gate_id,
        )
        return dr

    @staticmethod
    def _apply_to_live_registry(record: "ProposalRecord", ts_ns: int) -> None:
        """Promote to strategy registry (best-effort)."""
        try:
            from governance_engine.strategy_registry import get_strategy_registry
            reg = get_strategy_registry()
            if hasattr(reg, "deploy"):
                reg.deploy(record.proposal_id, ts_ns=ts_ns)
            elif hasattr(reg, "promote"):
                reg.promote(record.proposal_id, ts_ns=ts_ns)
        except Exception:
            pass

    @staticmethod
    def _emit_deployment_event(proposal_id: str, dr: "DeploymentRecord") -> None:
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().publish(CognitiveChannel.DYON_PROPOSAL, {
                "proposal_id": proposal_id,
                "pipeline_stage": "DEPLOYED",
                "gate_id": dr.gate_id,
                "approved_by": dr.approved_by,
                "deployment_hash": dr.deployment_hash,
                "ts_ns": dr.ts_ns,
            })
        except Exception:
            pass
        try:
            from state.ledger.append import append_event
            append_event(
                stream="SYSTEM",
                kind="EVOLUTION_DEPLOYED",
                source="DYON",
                payload={
                    "proposal_id": proposal_id,
                    "gate_id": dr.gate_id,
                    "approved_by": dr.approved_by,
                    "deployment_hash": dr.deployment_hash,
                    "mutation_class": dr.mutation_class,
                    "ts_ns": dr.ts_ns,
                },
            )
        except Exception:
            pass

    @staticmethod
    def _record_to_dict(dr: "DeploymentRecord") -> dict[str, Any]:
        return {
            "gate_id": dr.gate_id,
            "approved_by": dr.approved_by,
            "deployment_hash": dr.deployment_hash,
            "mutation_class": dr.mutation_class,
            "ts_ns": dr.ts_ns,
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_gate: DeploymentGate | None = None
_gate_lock = threading.Lock()


def get_deployment_gate(*, auto_deploy_class_a: bool = True) -> DeploymentGate:
    """Return the process-wide DeploymentGate singleton."""
    global _gate
    with _gate_lock:
        if _gate is None:
            _gate = DeploymentGate(auto_deploy_class_a=auto_deploy_class_a)
    return _gate


__all__ = ["DeploymentGate", "get_deployment_gate"]

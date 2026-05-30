"""governance_engine.hardening.mutation_firewall — Mutation containment layer.

Every mutation proposal MUST pass through the MutationFirewall before reaching
the EvolutionLifecycleCoordinator.  The firewall enforces:

  CLASS_A  — auto-pass if source trust score ≥ TRUST_PASS_THRESHOLD
  CLASS_B  — pass if trust score ≥ TRUST_PASS_THRESHOLD + operator acknowledgement
  CLASS_C  — ALWAYS quarantined; requires explicit dual sign-off before release

Quarantine:
  Quarantined proposals are held in an in-memory queue with a TTL.  A second
  governor must call release_quarantine() before the proposal proceeds.  After
  TTL expiry the proposal is automatically expired (never silently promoted).

All firewall decisions are appended to the authority ledger.

Authority (L1): stdlib only at module level.
INV-15: ts_ns is caller-supplied.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

_logger = logging.getLogger(__name__)

TRUST_PASS_THRESHOLD: float = 0.50    # minimum trust for CLASS_A/B auto-pass
QUARANTINE_TTL_NS: int = 300_000_000_000  # 5 minutes in nanoseconds


class FirewallDecision(StrEnum):
    PASS = "PASS"
    QUARANTINE = "QUARANTINE"
    BLOCK = "BLOCK"


@dataclass(frozen=True, slots=True)
class FirewallVerdict:
    """Result of one firewall check."""

    proposal_id: str
    mutation_class: str
    source_engine: str
    decision: FirewallDecision
    reason: str
    ts_ns: int


@dataclass
class QuarantineEntry:
    """Mutable quarantine record — released by dual sign-off."""

    proposal_id: str
    mutation_class: str
    source_engine: str
    description: str
    ts_ns_quarantined: int
    sign_offs: list[str] = field(default_factory=list)   # governor IDs
    released: bool = False
    expired: bool = False

    def is_expired(self, now_ns: int) -> bool:
        return (now_ns - self.ts_ns_quarantined) > QUARANTINE_TTL_NS


class MutationFirewall:
    """Containment layer between mutation sources and the lifecycle coordinator.

    Args:
        required_class_c_signoffs: number of distinct governors required to
            release a CLASS_C quarantine entry (default 2).
    """

    def __init__(self, *, required_class_c_signoffs: int = 2) -> None:
        self._lock = threading.Lock()
        self._required_c = max(1, required_class_c_signoffs)
        self._quarantine: dict[str, QuarantineEntry] = {}
        self._block_log: list[FirewallVerdict] = []
        self._pass_count: int = 0
        self._quarantine_count: int = 0
        self._block_count: int = 0

    # ------------------------------------------------------------------
    # Main check
    # ------------------------------------------------------------------

    def check(
        self,
        *,
        proposal_id: str,
        mutation_class: str,
        source_engine: str,
        description: str,
        ts_ns: int,
    ) -> FirewallVerdict:
        """Evaluate a proposed mutation against the firewall rules.

        Returns a FirewallVerdict with PASS | QUARANTINE | BLOCK.
        The caller MUST honour the verdict — submitting a QUARANTINE or BLOCK
        to the lifecycle coordinator is a firewall bypass violation.
        """
        # Expire stale quarantine entries
        self._expire_stale(ts_ns)

        # Trust score check
        trust = self._source_trust(source_engine)

        decision, reason = self._evaluate(mutation_class, source_engine, trust, ts_ns)
        verdict = FirewallVerdict(
            proposal_id=proposal_id,
            mutation_class=mutation_class,
            source_engine=source_engine,
            decision=decision,
            reason=reason,
            ts_ns=ts_ns,
        )

        with self._lock:
            if decision is FirewallDecision.PASS:
                self._pass_count += 1
            elif decision is FirewallDecision.QUARANTINE:
                self._quarantine_count += 1
                self._quarantine[proposal_id] = QuarantineEntry(
                    proposal_id=proposal_id,
                    mutation_class=mutation_class,
                    source_engine=source_engine,
                    description=description,
                    ts_ns_quarantined=ts_ns,
                )
            else:
                self._block_count += 1
                self._block_log.append(verdict)
                if len(self._block_log) > 500:
                    self._block_log = self._block_log[-250:]

        self._audit(verdict)
        if decision is not FirewallDecision.PASS:
            self._emit_containment_event(verdict)
        _logger.debug(
            "MutationFirewall[%s] class=%s trust=%.2f → %s: %s",
            proposal_id[:16], mutation_class, trust, decision.value, reason,
        )
        return verdict

    # ------------------------------------------------------------------
    # Quarantine release (dual sign-off for CLASS_C)
    # ------------------------------------------------------------------

    def sign_off(self, proposal_id: str, governor_id: str, ts_ns: int) -> bool:
        """Add a governor sign-off to a quarantined proposal.

        Returns True if the proposal is now released (enough sign-offs collected).
        """
        with self._lock:
            entry = self._quarantine.get(proposal_id)
            if entry is None or entry.released or entry.expired:
                return False
            if entry.is_expired(ts_ns):
                entry.expired = True
                return False
            if governor_id not in entry.sign_offs:
                entry.sign_offs.append(governor_id)
            needed = self._required_c if entry.mutation_class == "CLASS_C" else 1
            if len(entry.sign_offs) >= needed:
                entry.released = True
                return True
        return False

    def is_released(self, proposal_id: str) -> bool:
        with self._lock:
            entry = self._quarantine.get(proposal_id)
            return entry is not None and entry.released

    def quarantine_status(self, proposal_id: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._quarantine.get(proposal_id)
        if entry is None:
            return None
        return {
            "proposal_id": entry.proposal_id,
            "mutation_class": entry.mutation_class,
            "source_engine": entry.source_engine,
            "sign_offs": list(entry.sign_offs),
            "sign_offs_needed": self._required_c if entry.mutation_class == "CLASS_C" else 1,
            "released": entry.released,
            "expired": entry.expired,
            "ts_ns_quarantined": entry.ts_ns_quarantined,
        }

    # ------------------------------------------------------------------
    # Read surface
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            active_quarantine = [
                self.quarantine_status(pid)
                for pid, e in self._quarantine.items()
                if not e.released and not e.expired
            ]
            recent_blocks = [
                {"proposal_id": v.proposal_id, "class": v.mutation_class,
                 "reason": v.reason, "ts_ns": v.ts_ns}
                for v in self._block_log[-10:]
            ]
        return {
            "pass_count": self._pass_count,
            "quarantine_count": self._quarantine_count,
            "block_count": self._block_count,
            "active_quarantine": active_quarantine,
            "recent_blocks": recent_blocks,
            "required_class_c_signoffs": self._required_c,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _evaluate(
        self, mutation_class: str, source_engine: str, trust: float, ts_ns: int
    ) -> tuple[FirewallDecision, str]:
        if trust < 0.10:
            return FirewallDecision.BLOCK, f"source {source_engine!r} trust={trust:.3f} revoked"

        if mutation_class == "CLASS_C":
            return FirewallDecision.QUARANTINE, "CLASS_C always quarantined pending dual sign-off"

        if trust < TRUST_PASS_THRESHOLD:
            return (
                FirewallDecision.QUARANTINE,
                f"trust={trust:.3f} below threshold={TRUST_PASS_THRESHOLD} for class={mutation_class}",
            )

        return FirewallDecision.PASS, f"class={mutation_class} trust={trust:.3f} ≥ threshold"

    @staticmethod
    def _source_trust(source_engine: str) -> float:
        try:
            from governance_engine.hardening.trust_scorer import get_trust_scorer
            return get_trust_scorer().score(source_engine)
        except Exception:
            return 0.0  # fail-closed: unavailable scorer means untrusted, not fully-trusted

    def _expire_stale(self, ts_ns: int) -> None:
        with self._lock:
            for entry in self._quarantine.values():
                if not entry.released and not entry.expired and entry.is_expired(ts_ns):
                    entry.expired = True
                    _logger.info(
                        "MutationFirewall: quarantine TTL expired for %s",
                        entry.proposal_id[:16],
                    )

    @staticmethod
    def _audit(verdict: FirewallVerdict) -> None:
        try:
            from state.ledger.append import append_event
            append_event(
                stream="GOVERNANCE",
                kind="MUTATION_FIREWALL",
                source="governance_engine",
                payload={
                    "proposal_id": verdict.proposal_id,
                    "mutation_class": verdict.mutation_class,
                    "source_engine": verdict.source_engine,
                    "decision": verdict.decision.value,
                    "reason": verdict.reason,
                    "ts_ns": verdict.ts_ns,
                },
            )
        except Exception:
            pass

    @staticmethod
    def _emit_containment_event(verdict: FirewallVerdict) -> None:
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().publish(CognitiveChannel.DYON_VIOLATION, {
                "source": "mutation_firewall",
                "proposal_id": verdict.proposal_id,
                "decision": verdict.decision.value,
                "reason": verdict.reason,
                "ts_ns": verdict.ts_ns,
            })
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_firewall: MutationFirewall | None = None
_firewall_lock = threading.Lock()


def get_mutation_firewall(*, required_class_c_signoffs: int = 2) -> MutationFirewall:
    global _firewall
    with _firewall_lock:
        if _firewall is None:
            _firewall = MutationFirewall(required_class_c_signoffs=required_class_c_signoffs)
    return _firewall


__all__ = [
    "FirewallDecision",
    "FirewallVerdict",
    "MutationFirewall",
    "QuarantineEntry",
    "TRUST_PASS_THRESHOLD",
    "get_mutation_firewall",
]

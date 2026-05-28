"""
cognitive_governance/causal_consistency.py
DIX VISION v42.2 — Causal Consistency Guard

Validates attribution chains for two violation types:

  CAUSAL_GHOST — a decision cites a signal that is timestamped AFTER
  the decision itself. This indicates either a replay ordering bug or
  a look-ahead bias leaking into real decision attribution.

  CAUSAL_DOMAIN_LEAK — a SYSTEM-domain event (hazard detection, system
  monitor) appears in the causal chain of a MARKET-domain decision
  (trade execution). Per the manifest's authority model, Dyon's hazard
  detections may gate Indira's execution via Governance, but they must
  NEVER appear as direct causal parents of trade decisions. The correct
  causal shape is: Dyon hazard → Governance mode change → Indira blocked.
"""

from __future__ import annotations

import threading

from core.contracts.cognitive_governance import (
    CausalConsistencyReport,
    CognitiveSeverity,
    CognitiveViolationKind,
)
from state.ledger.event_store import append_event

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MARKET_DOMAIN = "market"
SYSTEM_DOMAIN = "system"


class CausalConsistencyGuard:
    """
    Validates causal attribution chains for ghost causality and domain leaks.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_decision(
        self,
        decision_id: str,
        ts_ns: int,
        domain: str,
        causal_parents: list[dict],
    ) -> CausalConsistencyReport:
        """
        Register a decision and validate its causal attribution chain.

        causal_parents: list of dicts, each with keys:
          - "signal_id": str
          - "ts_ns": int        — timestamp of the parent signal
          - "domain": str       — domain of the parent signal

        Returns CausalConsistencyReport. Callers should log non-passed
        reports to the governance review queue.
        """
        ghost_details = self._check_ghost_causality(ts_ns, causal_parents)
        leak_details = self._check_domain_leak(domain, causal_parents)

        all_details = ghost_details + leak_details
        violations: list[CognitiveViolationKind] = []

        if ghost_details:
            violations.append(CognitiveViolationKind.CAUSAL_GHOST)
        if leak_details:
            violations.append(CognitiveViolationKind.CAUSAL_DOMAIN_LEAK)

        passed = len(violations) == 0
        detail = "; ".join(all_details) if all_details else "OK"

        # Severity
        if CognitiveViolationKind.CAUSAL_GHOST in violations:
            severity = CognitiveSeverity.CRITICAL  # look-ahead bias is a hard error
        elif CognitiveViolationKind.CAUSAL_DOMAIN_LEAK in violations:
            severity = CognitiveSeverity.HIGH
        else:
            severity = CognitiveSeverity.INFO

        report = CausalConsistencyReport(
            ts_ns=ts_ns,
            decision_id=decision_id,
            passed=passed,
            violations=tuple(violations),
            detail=detail,
        )

        if not passed:
            append_event(
                "GOVERNANCE",
                "COGOV_CAUSAL_CONSISTENCY",
                "cognitive_governance.causal_consistency",
                {
                    "decision_id": decision_id,
                    "domain": domain,
                    "passed": passed,
                    "severity": severity.value,
                    "violations": [v.value for v in violations],
                    "n_parents": len(causal_parents),
                    "detail": detail,
                },
            )

        return report

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_ghost_causality(
        self, decision_ts_ns: int, parents: list[dict]
    ) -> list[str]:
        """
        Detect CAUSAL_GHOST: parent signals with ts_ns > decision ts_ns.

        A signal timestamped after the decision it supposedly caused is
        look-ahead bias — a replay ordering error or data leakage.
        """
        details: list[str] = []
        for p in parents:
            parent_ts = p.get("ts_ns", 0)
            signal_id = p.get("signal_id", "<unknown>")
            if parent_ts > decision_ts_ns:
                delta_ns = parent_ts - decision_ts_ns
                details.append(
                    f"CAUSAL_GHOST: signal={signal_id!r} "
                    f"ts_ns={parent_ts} > decision ts_ns={decision_ts_ns} "
                    f"(delta={delta_ns}ns — look-ahead bias)"
                )
        return details

    def _check_domain_leak(
        self, decision_domain: str, parents: list[dict]
    ) -> list[str]:
        """
        Detect CAUSAL_DOMAIN_LEAK: system-domain signals in market-domain
        decision attribution chains.

        System hazard signals must flow Dyon→Governance→mode_change→Indira,
        never as direct causal parents of trade decisions.
        """
        if decision_domain != MARKET_DOMAIN:
            return []

        details: list[str] = []
        for p in parents:
            parent_domain = p.get("domain", "")
            signal_id = p.get("signal_id", "<unknown>")
            if parent_domain == SYSTEM_DOMAIN:
                details.append(
                    f"CAUSAL_DOMAIN_LEAK: system-domain signal={signal_id!r} "
                    f"is a direct causal parent of market-domain decision. "
                    f"Correct path: Dyon hazard → Governance mode change → Indira blocked."
                )
        return details


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: CausalConsistencyGuard | None = None
_lock = threading.Lock()


def get_causal_consistency_guard() -> CausalConsistencyGuard:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = CausalConsistencyGuard()
    return _instance


__all__ = ["CausalConsistencyGuard", "get_causal_consistency_guard"]

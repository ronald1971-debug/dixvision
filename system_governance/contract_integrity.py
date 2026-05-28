"""
system_governance/contract_integrity.py
DIX VISION v42.2 — Contract Integrity Guard

Every inter-subsystem contract must be honoured at runtime. This guard
tracks registered contracts and validates that each subsystem:
  1. Has registered a contract (not NULL_CONTRACT)
  2. Exposes the expected interface (not INTERFACE_MISMATCH)
  3. Uses a compatible schema version (not VERSION_MISMATCH)
  4. Meets its SLA (not TIMEOUT_VIOLATION)
  5. Emits required audit events (not MISSING_LEDGER_EMIT)

Contract violations represent structural fragmentation — they are
HIGH or CRITICAL severity depending on whether they affect the
execution path.
"""

from __future__ import annotations

import threading
import time as _time
from collections import deque
from typing import Any

from core.contracts.system_governance import (
    ContractViolation,
    ContractViolationKind,
    SystemGovernanceSeverity,
)
from state.ledger.event_store import append_event


_MAX_HISTORY = 500


class ContractIntegrityGuard:
    """
    Validates inter-subsystem contract compliance.

    Thread-safe. Subsystems register their contracts via register_contract().
    The guard checks that all declared requirements are met and emits
    SYSGOV_CONTRACT_VIOLATION events for failures.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # subsystem → {"interface": set[str], "version": str, "emits_audit": bool}
        self._contracts: dict[str, dict] = {}
        self._violations: deque[ContractViolation] = deque(maxlen=_MAX_HISTORY)
        self._violation_count: int = 0

    # ------------------------------------------------------------------
    # Contract registration
    # ------------------------------------------------------------------

    def register_contract(
        self,
        subsystem: str,
        interface: set[str],
        version: str,
        emits_audit: bool = True,
    ) -> None:
        """
        Register a subsystem's contract.

        interface: set of method/attribute names the subsystem exposes.
        version: schema version string (e.g., "1.0").
        emits_audit: whether the subsystem emits governance events.
        """
        with self._lock:
            self._contracts[subsystem] = {
                "interface": set(interface),
                "version": version,
                "emits_audit": emits_audit,
                "registered_ts_ns": _time.time_ns(),
            }

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(
        self,
        source: str,
        target: str,
        required_interface: set[str] | None = None,
        required_version: str | None = None,
    ) -> list[ContractViolation]:
        """
        Validate that `target` satisfies `source`'s contract requirements.

        Returns a (possibly empty) list of ContractViolation records.
        All violations are also emitted to the ledger.
        """
        ts_ns = _time.time_ns()
        violations: list[ContractViolation] = []

        with self._lock:
            contract = self._contracts.get(target)

        if contract is None:
            v = ContractViolation(
                ts_ns=ts_ns,
                source=source,
                target=target,
                kind=ContractViolationKind.NULL_CONTRACT,
                severity=SystemGovernanceSeverity.HIGH,
                detail=f"{target!r} has no registered contract",
            )
            violations.append(v)
        else:
            if required_interface:
                missing = required_interface - contract["interface"]
                if missing:
                    v = ContractViolation(
                        ts_ns=ts_ns,
                        source=source,
                        target=target,
                        kind=ContractViolationKind.INTERFACE_MISMATCH,
                        severity=SystemGovernanceSeverity.HIGH,
                        detail=f"missing methods/attrs: {sorted(missing)}",
                    )
                    violations.append(v)

            if required_version and contract["version"] != required_version:
                v = ContractViolation(
                    ts_ns=ts_ns,
                    source=source,
                    target=target,
                    kind=ContractViolationKind.VERSION_MISMATCH,
                    severity=SystemGovernanceSeverity.WARNING,
                    detail=(
                        f"expected version={required_version!r}; "
                        f"got {contract['version']!r}"
                    ),
                )
                violations.append(v)

            if not contract["emits_audit"]:
                v = ContractViolation(
                    ts_ns=ts_ns,
                    source=source,
                    target=target,
                    kind=ContractViolationKind.MISSING_LEDGER_EMIT,
                    severity=SystemGovernanceSeverity.WARNING,
                    detail=f"{target!r} declared emits_audit=False",
                )
                violations.append(v)

        if violations:
            with self._lock:
                for v in violations:
                    self._violations.append(v)
                self._violation_count += len(violations)

            for v in violations:
                append_event(
                    "GOVERNANCE",
                    "SYSGOV_CONTRACT_VIOLATION",
                    "system_governance.contract_integrity",
                    {
                        "source": v.source,
                        "target": v.target,
                        "kind": v.kind.value,
                        "severity": v.severity.value,
                        "detail": v.detail,
                    },
                )

        return violations

    def record_sla_violation(
        self,
        source: str,
        target: str,
        elapsed_ns: int,
        sla_ns: int,
    ) -> ContractViolation:
        """Record a contract SLA timeout violation."""
        ts_ns = _time.time_ns()
        v = ContractViolation(
            ts_ns=ts_ns,
            source=source,
            target=target,
            kind=ContractViolationKind.TIMEOUT_VIOLATION,
            severity=SystemGovernanceSeverity.HIGH,
            detail=f"elapsed={elapsed_ns}ns > sla={sla_ns}ns",
        )
        with self._lock:
            self._violations.append(v)
            self._violation_count += 1

        append_event(
            "GOVERNANCE",
            "SYSGOV_CONTRACT_VIOLATION",
            "system_governance.contract_integrity",
            {
                "source": source,
                "target": target,
                "kind": v.kind.value,
                "severity": v.severity.value,
                "detail": v.detail,
            },
        )
        return v

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def registered_subsystems(self) -> list[str]:
        with self._lock:
            return list(self._contracts.keys())

    def violation_count(self) -> int:
        with self._lock:
            return self._violation_count

    def recent_violations(self, n: int = 20) -> list[ContractViolation]:
        with self._lock:
            items = list(self._violations)
        return items[-n:]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "registered_subsystems": len(self._contracts),
                "violation_count": self._violation_count,
                "history_size": len(self._violations),
            }


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: ContractIntegrityGuard | None = None
_lock = threading.Lock()


def get_contract_integrity_guard() -> ContractIntegrityGuard:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = ContractIntegrityGuard()
    return _instance


__all__ = ["ContractIntegrityGuard", "get_contract_integrity_guard"]

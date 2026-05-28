"""
system_governance/topology_guard.py
DIX VISION v42.2 — Topology Guard

Enforces the module topology rules that keep DIX VISION's architecture
coherent. The B1 constraint is the primary invariant: no direct
cross-engine import is permitted. All cross-domain communication must
flow through declared contracts and the event bus.

Violation kinds:
  B1_CROSS_ENGINE_IMPORT  — direct import between execution engines
  DOMAIN_BOUNDARY_BREACH  — import crossing execution↔system boundary
  UNDECLARED_DEPENDENCY   — runtime import not in declared dependency list
  CIRCULAR_IMPORT         — import cycle detected
"""

from __future__ import annotations

import threading
import time as _time
from collections import deque
from typing import Any

from core.contracts.system_governance import (
    SystemGovernanceSeverity,
    TopologyViolation,
    TopologyViolationKind,
)
from state.ledger.event_store import append_event


_MAX_HISTORY = 500

# Domains that may not import from each other directly (B1)
_B1_PROTECTED_DOMAINS = frozenset(
    {
        "execution_engine",
        "sensory",
        "indira",
        "dyon",
    }
)

# Execution path modules that must not import system infrastructure
_EXECUTION_DOMAIN = frozenset(
    {
        "execution_engine",
        "execution_engine.adapters",
        "execution_engine.router",
        "execution_engine.order_manager",
    }
)

_SYSTEM_DOMAIN = frozenset(
    {
        "system_governance",
        "operator_governance",
        "cognitive_governance",
        "financial_governance",
        "state",
    }
)


class TopologyGuard:
    """
    Detects and records illegal module topology events.

    Thread-safe. Callers invoke record_import() for every observed import
    (typically from an import hook or static analysis scan). The guard
    classifies each import and emits SYSGOV_TOPOLOGY_VIOLATION on failure.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # module → frozenset of declared allowed imports
        self._declared_deps: dict[str, frozenset[str]] = {}
        self._violations: deque[TopologyViolation] = deque(maxlen=_MAX_HISTORY)
        self._violation_count: int = 0

    # ------------------------------------------------------------------
    # Dependency declaration
    # ------------------------------------------------------------------

    def declare_dependencies(self, module: str, allowed: set[str]) -> None:
        """
        Declare the set of modules that `module` is allowed to import.

        Any import not in this set triggers UNDECLARED_DEPENDENCY.
        """
        with self._lock:
            self._declared_deps[module] = frozenset(allowed)

    # ------------------------------------------------------------------
    # Import recording
    # ------------------------------------------------------------------

    def record_import(self, importer: str, importee: str) -> list[TopologyViolation]:
        """
        Record an observed import and check it against topology rules.

        Returns any topology violations found. All violations are emitted
        to the governance ledger.
        """
        ts_ns = _time.time_ns()
        violations: list[TopologyViolation] = []

        # B1: cross-engine import check
        importer_domain = _get_top_domain(importer)
        importee_domain = _get_top_domain(importee)
        if (
            importer_domain in _B1_PROTECTED_DOMAINS
            and importee_domain in _B1_PROTECTED_DOMAINS
            and importer_domain != importee_domain
        ):
            violations.append(
                TopologyViolation(
                    ts_ns=ts_ns,
                    importer=importer,
                    importee=importee,
                    kind=TopologyViolationKind.B1_CROSS_ENGINE_IMPORT,
                    severity=SystemGovernanceSeverity.CRITICAL,
                    detail=(
                        f"B1 violation: {importer_domain!r} imports from "
                        f"{importee_domain!r} — cross-engine imports are forbidden"
                    ),
                )
            )

        # Domain boundary: execution importing system infrastructure
        if importer_domain in _EXECUTION_DOMAIN and importee_domain in _SYSTEM_DOMAIN:
            violations.append(
                TopologyViolation(
                    ts_ns=ts_ns,
                    importer=importer,
                    importee=importee,
                    kind=TopologyViolationKind.DOMAIN_BOUNDARY_BREACH,
                    severity=SystemGovernanceSeverity.HIGH,
                    detail=(
                        f"execution module {importer!r} imports system module "
                        f"{importee!r} — use the event bus instead"
                    ),
                )
            )

        # Undeclared dependency check
        with self._lock:
            declared = self._declared_deps.get(importer)
        if declared is not None and importee not in declared:
            violations.append(
                TopologyViolation(
                    ts_ns=ts_ns,
                    importer=importer,
                    importee=importee,
                    kind=TopologyViolationKind.UNDECLARED_DEPENDENCY,
                    severity=SystemGovernanceSeverity.WARNING,
                    detail=(
                        f"{importer!r} imports {importee!r} which is not in "
                        "its declared dependency list"
                    ),
                )
            )

        if violations:
            with self._lock:
                for v in violations:
                    self._violations.append(v)
                self._violation_count += len(violations)

            for v in violations:
                append_event(
                    "GOVERNANCE",
                    "SYSGOV_TOPOLOGY_VIOLATION",
                    "system_governance.topology_guard",
                    {
                        "importer": v.importer,
                        "importee": v.importee,
                        "kind": v.kind.value,
                        "severity": v.severity.value,
                        "detail": v.detail,
                    },
                )

        return violations

    def record_circular_import(self, cycle: list[str]) -> TopologyViolation:
        """Record a detected circular import cycle."""
        ts_ns = _time.time_ns()
        cycle_str = " → ".join(cycle)
        v = TopologyViolation(
            ts_ns=ts_ns,
            importer=cycle[0] if cycle else "unknown",
            importee=cycle[-1] if len(cycle) > 1 else "unknown",
            kind=TopologyViolationKind.CIRCULAR_IMPORT,
            severity=SystemGovernanceSeverity.CRITICAL,
            detail=f"import cycle detected: {cycle_str}",
        )
        with self._lock:
            self._violations.append(v)
            self._violation_count += 1

        append_event(
            "GOVERNANCE",
            "SYSGOV_TOPOLOGY_VIOLATION",
            "system_governance.topology_guard",
            {
                "importer": v.importer,
                "importee": v.importee,
                "kind": v.kind.value,
                "severity": v.severity.value,
                "detail": v.detail,
            },
        )
        return v

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def violation_count(self) -> int:
        with self._lock:
            return self._violation_count

    def recent_violations(self, n: int = 20) -> list[TopologyViolation]:
        with self._lock:
            items = list(self._violations)
        return items[-n:]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "declared_modules": len(self._declared_deps),
                "violation_count": self._violation_count,
                "history_size": len(self._violations),
            }


def _get_top_domain(module: str) -> str:
    """Return the top-level package name of a module path."""
    return module.split(".")[0]


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: TopologyGuard | None = None
_lock = threading.Lock()


def get_topology_guard() -> TopologyGuard:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = TopologyGuard()
    return _instance


__all__ = ["TopologyGuard", "get_topology_guard"]

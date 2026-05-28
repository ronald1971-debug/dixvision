"""
cognitive_governance/strategy_lineage_guard.py
DIX VISION v42.2 — Strategy Lineage Guard

Every strategy in the registry must have provenance: either a
human-authored seed (lineage_id=None, operator_authored=True) or
a governance-approved mutation of a strategy with valid lineage.

The guard maintains a DAG of strategy lineage and enforces:

  LINEAGE_GAP   — a strategy claims to evolve from a parent that does
                  not exist in the registry.

  LINEAGE_CYCLE — a strategy's ancestry chain contains a cycle
                  (strategy A evolved from B which evolved from A).
                  This should never happen in a well-managed registry
                  but can occur with replay errors or manual edits.

Chain depth is capped at MAX_CHAIN_DEPTH. Chains exceeding this are
rejected as LINEAGE_GAP (the ancestry is unverifiable).
"""

from __future__ import annotations

import threading

from core.contracts.cognitive_governance import (
    CognitiveSeverity,
    CognitiveViolationKind,
    LineageValidationResult,
)
from state.ledger.event_store import append_event

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_CHAIN_DEPTH = 50


class StrategyLineageGuard:
    """
    Maintains a strategy lineage DAG and enforces ancestry integrity.
    """

    def __init__(self) -> None:
        # strategy_id → {"parent_id": str | None, "operator_authored": bool, "ts_ns": int}
        self._registry: dict[str, dict] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_strategy(
        self,
        strategy_id: str,
        parent_id: str | None,
        operator_authored: bool,
        ts_ns: int,
    ) -> LineageValidationResult:
        """
        Register a new strategy and validate its lineage.

        Seeds (operator_authored=True, parent_id=None) are always valid.
        AI-generated mutations must cite a parent_id that exists in the
        registry.

        Returns LineageValidationResult. Callers must check result.passed
        before admitting the strategy to the live registry.
        """
        violations: list[CognitiveViolationKind] = []
        detail_parts: list[str] = []

        with self._lock:
            # Check for lineage gap (parent doesn't exist)
            if parent_id is not None and parent_id not in self._registry:
                violations.append(CognitiveViolationKind.LINEAGE_GAP)
                detail_parts.append(
                    f"parent_id={parent_id!r} not in registry; "
                    "cannot verify ancestry"
                )

            # Register the strategy (even if invalid, so we can detect cycles)
            self._registry[strategy_id] = {
                "parent_id": parent_id,
                "operator_authored": operator_authored,
                "ts_ns": ts_ns,
            }

            # Check for cycles
            if self._has_cycle(strategy_id):
                violations.append(CognitiveViolationKind.LINEAGE_CYCLE)
                detail_parts.append(
                    f"strategy_id={strategy_id!r} introduces a cycle in the lineage DAG"
                )

            # Check chain depth
            depth = self._chain_depth(strategy_id)

        if depth > MAX_CHAIN_DEPTH:
            violations.append(CognitiveViolationKind.LINEAGE_GAP)
            detail_parts.append(
                f"chain_depth={depth} > MAX_CHAIN_DEPTH={MAX_CHAIN_DEPTH}; "
                "ancestry unverifiable"
            )

        passed = len(violations) == 0
        detail = "; ".join(detail_parts) if detail_parts else f"OK (depth={depth})"

        severity = CognitiveSeverity.INFO
        if CognitiveViolationKind.LINEAGE_CYCLE in violations:
            severity = CognitiveSeverity.CRITICAL
        elif CognitiveViolationKind.LINEAGE_GAP in violations:
            severity = CognitiveSeverity.HIGH

        report = LineageValidationResult(
            ts_ns=ts_ns,
            strategy_id=strategy_id,
            chain_depth=depth,
            passed=passed,
            violations=tuple(violations),
            detail=detail,
        )

        append_event(
            "GOVERNANCE",
            "COGOV_LINEAGE_VALIDATED",
            "cognitive_governance.strategy_lineage_guard",
            {
                "strategy_id": strategy_id,
                "parent_id": parent_id,
                "operator_authored": operator_authored,
                "chain_depth": depth,
                "passed": passed,
                "severity": severity.value,
                "violations": [v.value for v in violations],
                "detail": detail,
            },
        )

        return report

    def validate_lineage(self, strategy_id: str) -> LineageValidationResult:
        """
        Re-validate the lineage of an already-registered strategy.

        Useful for periodic integrity sweeps of the strategy registry.
        """
        from system.time_source import wall_ns
        ts_ns = wall_ns()

        with self._lock:
            node = self._registry.get(strategy_id)
            if node is None:
                return LineageValidationResult(
                    ts_ns=ts_ns,
                    strategy_id=strategy_id,
                    chain_depth=0,
                    passed=False,
                    violations=(CognitiveViolationKind.LINEAGE_GAP,),
                    detail=f"strategy_id={strategy_id!r} not found in registry",
                )

            has_cycle = self._has_cycle(strategy_id)
            depth = self._chain_depth(strategy_id)
            parent_id = node.get("parent_id")

        violations: list[CognitiveViolationKind] = []
        detail_parts: list[str] = []

        if has_cycle:
            violations.append(CognitiveViolationKind.LINEAGE_CYCLE)
            detail_parts.append("cycle detected in lineage DAG")

        if depth > MAX_CHAIN_DEPTH:
            violations.append(CognitiveViolationKind.LINEAGE_GAP)
            detail_parts.append(f"depth={depth} exceeds MAX_CHAIN_DEPTH={MAX_CHAIN_DEPTH}")

        with self._lock:
            if parent_id is not None and parent_id not in self._registry:
                violations.append(CognitiveViolationKind.LINEAGE_GAP)
                detail_parts.append(f"parent_id={parent_id!r} missing from registry")

        passed = len(violations) == 0
        detail = "; ".join(detail_parts) if detail_parts else f"OK (depth={depth})"

        return LineageValidationResult(
            ts_ns=ts_ns,
            strategy_id=strategy_id,
            chain_depth=depth,
            passed=passed,
            violations=tuple(violations),
            detail=detail,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _has_cycle(self, strategy_id: str) -> bool:
        """
        DFS cycle detection from strategy_id.

        Assumes _lock is held by caller (or called from within lock context).
        """
        visited: set[str] = set()
        current: str | None = strategy_id

        while current is not None:
            if current in visited:
                return True
            visited.add(current)
            node = self._registry.get(current)
            if node is None:
                break
            current = node.get("parent_id")

        return False

    def _chain_depth(self, strategy_id: str) -> int:
        """
        Compute the depth of the ancestry chain.

        Returns the number of ancestors (0 = root/seed).
        Assumes _lock is held by caller.
        """
        depth = 0
        current: str | None = strategy_id
        visited: set[str] = set()

        while current is not None:
            if current in visited:
                # Cycle — stop counting
                break
            visited.add(current)
            node = self._registry.get(current)
            if node is None:
                break
            parent = node.get("parent_id")
            if parent is None:
                break
            depth += 1
            current = parent
            if depth > MAX_CHAIN_DEPTH:
                break

        return depth


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: StrategyLineageGuard | None = None
_lock = threading.Lock()


def get_strategy_lineage_guard() -> StrategyLineageGuard:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = StrategyLineageGuard()
    return _instance


__all__ = ["StrategyLineageGuard", "get_strategy_lineage_guard"]

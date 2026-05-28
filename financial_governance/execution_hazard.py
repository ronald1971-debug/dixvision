"""
financial_governance/execution_hazard.py
DIX VISION v42.2 — Execution Hazard Detector

Detects hazards in the execution path before orders are placed.
An execution hazard is any condition that makes order placement
unreliable or risky:
  - Adapter/routing failures
  - Exchange unreliability (circuit breaker open)
  - Excessive slippage
  - Drawdown limit reached
  - Capital rate exceeded

Hazards can auto-block orders (auto_blocked=True) or just warn.
The operator decides whether to resume after a hazard is cleared.
"""

from __future__ import annotations

import threading
import time as _time
from collections import deque
from typing import Any

from core.contracts.financial_governance import (
    ExecutionHazardRecord,
    FinancialSeverity,
    FinancialViolationKind,
)
from state.ledger.event_store import append_event


_MAX_HISTORY = 500

# Hazard kinds that auto-block execution
_AUTO_BLOCK_KINDS = frozenset(
    {
        FinancialViolationKind.EXCHANGE_UNRELIABLE,
        FinancialViolationKind.DRAWDOWN_LIMIT,
        FinancialViolationKind.SLIPPAGE_EXCESSIVE,
    }
)


class ExecutionHazardDetector:
    """
    Detects and records execution path hazards.

    Thread-safe. Callers report hazards via record_hazard() and check
    whether execution is currently blocked via is_blocked().
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: deque[ExecutionHazardRecord] = deque(maxlen=_MAX_HISTORY)
        # adapter_id → set of currently-active auto-blocking hazard kinds
        self._active_blocks: dict[str, set[FinancialViolationKind]] = {}
        self._violation_count: int = 0

    # ------------------------------------------------------------------
    # Hazard recording
    # ------------------------------------------------------------------

    def record_hazard(
        self,
        adapter_id: str,
        hazard_kind: FinancialViolationKind,
        description: str,
        severity: FinancialSeverity = FinancialSeverity.HIGH,
    ) -> ExecutionHazardRecord:
        """
        Record an execution hazard for an adapter.

        Auto-blocks execution for adapter_id if hazard_kind is in
        _AUTO_BLOCK_KINDS.
        """
        ts_ns = _time.time_ns()
        auto_blocked = hazard_kind in _AUTO_BLOCK_KINDS

        record = ExecutionHazardRecord(
            ts_ns=ts_ns,
            adapter_id=adapter_id,
            hazard_kind=hazard_kind,
            description=description,
            severity=severity,
            auto_blocked=auto_blocked,
        )

        with self._lock:
            self._records.append(record)
            self._violation_count += 1
            if auto_blocked:
                self._active_blocks.setdefault(adapter_id, set()).add(hazard_kind)

        append_event(
            "GOVERNANCE",
            "FINGOV_EXECUTION_HAZARD",
            "financial_governance.execution_hazard",
            {
                "adapter_id": adapter_id,
                "hazard_kind": hazard_kind.value,
                "description": description,
                "severity": severity.value,
                "auto_blocked": auto_blocked,
            },
        )

        return record

    def clear_hazard(
        self,
        adapter_id: str,
        hazard_kind: FinancialViolationKind,
    ) -> bool:
        """
        Clear an auto-blocking hazard for an adapter.

        Returns True if the hazard was active and has been cleared.
        Only the operator should call this to resume blocked execution.
        """
        with self._lock:
            blocks = self._active_blocks.get(adapter_id, set())
            if hazard_kind not in blocks:
                return False
            blocks.discard(hazard_kind)
            if not blocks:
                self._active_blocks.pop(adapter_id, None)

        append_event(
            "GOVERNANCE",
            "FINGOV_HAZARD_CLEARED",
            "financial_governance.execution_hazard",
            {
                "adapter_id": adapter_id,
                "hazard_kind": hazard_kind.value,
            },
        )
        return True

    # ------------------------------------------------------------------
    # Gate
    # ------------------------------------------------------------------

    def is_blocked(self, adapter_id: str) -> bool:
        """Return True if the adapter has any active auto-blocking hazard."""
        with self._lock:
            return bool(self._active_blocks.get(adapter_id))

    def any_blocked(self) -> bool:
        """Return True if any adapter is currently blocked."""
        with self._lock:
            return any(bool(v) for v in self._active_blocks.values())

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def violation_count(self) -> int:
        with self._lock:
            return self._violation_count

    def recent_records(self, n: int = 20) -> list[ExecutionHazardRecord]:
        with self._lock:
            items = list(self._records)
        return items[-n:]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "blocked_adapters": list(self._active_blocks.keys()),
                "violation_count": self._violation_count,
                "history_size": len(self._records),
            }


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: ExecutionHazardDetector | None = None
_lock = threading.Lock()


def get_execution_hazard_detector() -> ExecutionHazardDetector:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = ExecutionHazardDetector()
    return _instance


__all__ = ["ExecutionHazardDetector", "get_execution_hazard_detector"]

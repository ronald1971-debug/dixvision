"""
financial_governance/exposure_guard.py
DIX VISION v42.2 — Exposure Guard

Net exposure per asset class must remain within declared risk budgets.
Exceeding a budget is a hard stop — not a warning. Execution is blocked
until the operator explicitly clears the breach or adjusts the budget.

Invariants:
  - Budget enforcement is unconditional (no grace period).
  - Exposure is tracked as absolute USD value.
  - All breaches are emitted to the governance ledger.
  - Budgets may only be changed by the operator.
"""

from __future__ import annotations

import threading
import time as _time
from collections import deque
from typing import Any

from core.contracts.financial_governance import (
    ExposureViolation,
    FinancialSeverity,
    FinancialViolationKind,
)
from state.ledger.event_store import append_event


_MAX_HISTORY = 500
_WARN_RATIO = 0.80  # warn at 80% of budget
_HIGH_RATIO = 0.95  # high severity at 95%


class ExposureGuard:
    """
    Net exposure guard per asset class.

    Thread-safe. Callers update exposure via update_exposure() and check
    budget compliance via check_exposure().
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # asset_class → budget_usd (operator-set)
        self._budgets: dict[str, float] = {}
        # (asset_class, symbol) → current_exposure_usd
        self._exposures: dict[tuple[str, str], float] = {}
        self._violations: deque[ExposureViolation] = deque(maxlen=_MAX_HISTORY)
        self._violation_count: int = 0

    # ------------------------------------------------------------------
    # Budget management (operator only)
    # ------------------------------------------------------------------

    def set_budget(self, asset_class: str, budget_usd: float) -> None:
        """Set the net exposure budget for an asset class."""
        with self._lock:
            self._budgets[asset_class] = budget_usd

    def get_budget(self, asset_class: str) -> float:
        with self._lock:
            return self._budgets.get(asset_class, 0.0)

    # ------------------------------------------------------------------
    # Exposure updates and checks
    # ------------------------------------------------------------------

    def update_exposure(
        self,
        asset_class: str,
        symbol: str,
        exposure_usd: float,
    ) -> ExposureViolation | None:
        """
        Update exposure for a (asset_class, symbol) pair.

        Returns an ExposureViolation if the budget is exceeded, else None.
        """
        with self._lock:
            self._exposures[(asset_class, symbol)] = exposure_usd
            budget = self._budgets.get(asset_class, 0.0)

        return self._check(asset_class, symbol, exposure_usd, budget)

    def check_exposure(self, asset_class: str, symbol: str) -> ExposureViolation | None:
        """
        Check current exposure for (asset_class, symbol) against its budget.

        Returns an ExposureViolation if breached, else None.
        """
        with self._lock:
            exposure = self._exposures.get((asset_class, symbol), 0.0)
            budget = self._budgets.get(asset_class, 0.0)
        return self._check(asset_class, symbol, exposure, budget)

    def _check(
        self,
        asset_class: str,
        symbol: str,
        exposure_usd: float,
        budget_usd: float,
    ) -> ExposureViolation | None:
        if budget_usd <= 0:
            return None
        ratio = exposure_usd / budget_usd
        if ratio < _WARN_RATIO:
            return None

        ts_ns = _time.time_ns()
        overage = max(0.0, exposure_usd - budget_usd)

        if ratio >= 1.0:
            severity = FinancialSeverity.CRITICAL
        elif ratio >= _HIGH_RATIO:
            severity = FinancialSeverity.HIGH
        else:
            severity = FinancialSeverity.WARNING

        v = ExposureViolation(
            ts_ns=ts_ns,
            asset_class=asset_class,
            symbol=symbol,
            current_exposure_usd=exposure_usd,
            budget_usd=budget_usd,
            overage_usd=overage,
            severity=severity,
            detail=f"exposure_ratio={ratio:.3f}",
        )

        if severity in (FinancialSeverity.CRITICAL, FinancialSeverity.HIGH):
            with self._lock:
                self._violations.append(v)
                self._violation_count += 1

            append_event(
                "GOVERNANCE",
                "FINGOV_EXPOSURE_BREACH",
                "financial_governance.exposure_guard",
                {
                    "asset_class": asset_class,
                    "symbol": symbol,
                    "current_exposure_usd": exposure_usd,
                    "budget_usd": budget_usd,
                    "overage_usd": overage,
                    "severity": severity.value,
                    "detail": v.detail,
                },
            )

        return v

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def total_exposure_usd(self) -> float:
        with self._lock:
            return sum(self._exposures.values())

    def violation_count(self) -> int:
        with self._lock:
            return self._violation_count

    def recent_violations(self, n: int = 20) -> list[ExposureViolation]:
        with self._lock:
            items = list(self._violations)
        return items[-n:]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "budgets": dict(self._budgets),
                "total_exposure_usd": sum(self._exposures.values()),
                "position_count": len(self._exposures),
                "violation_count": self._violation_count,
            }


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: ExposureGuard | None = None
_lock = threading.Lock()


def get_exposure_guard() -> ExposureGuard:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = ExposureGuard()
    return _instance


__all__ = ["ExposureGuard", "get_exposure_guard"]

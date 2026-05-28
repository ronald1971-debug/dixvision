"""
financial_governance/engine.py
DIX VISION v42.2 — Financial Governance Engine

Central coordinator for capital integrity. Delegates to the 6 specialist
guards, aggregates their state into FinancialGovernanceStatus, and emits
periodic FINGOV_STATUS events to the governance ledger.

Priority in the architecture:
  - Development phases: P4 (lowest) — cognitive integrity comes first
  - Live deployment:    P2 (co-equal with operator sovereignty)

Responsibilities:
  - Hold lazy references to all 6 guards
  - Provide check_all() → FinancialGovernanceStatus
  - Provide is_execution_safe() as the financial execution gate
  - Emit FINGOV_STATUS periodically (default: every 60 seconds)
  - Auto-arm the kill switch when drawdown or exposure limits are critically breached

The engine never executes trades. It gates and reports.
"""

from __future__ import annotations

import threading
import time as _time
from typing import Any

from core.contracts.financial_governance import (
    FinancialGovernanceStatus,
    FinancialSeverity,
    FinancialViolationKind,
    KillSwitchState,
)
from state.ledger.event_store import append_event

from financial_governance.capital_throttle import (
    CapitalThrottle,
    get_capital_throttle,
)
from financial_governance.execution_hazard import (
    ExecutionHazardDetector,
    get_execution_hazard_detector,
)
from financial_governance.exposure_guard import (
    ExposureGuard,
    get_exposure_guard,
)
from financial_governance.kill_switch import (
    KillSwitch,
    get_kill_switch,
)
from financial_governance.leverage_monitor import (
    LeverageMonitor,
    get_leverage_monitor,
)
from financial_governance.liquidation_sentinel import (
    LiquidationSentinel,
    get_liquidation_sentinel,
)


class FinancialGovernanceEngine:
    """
    Central coordinator for all capital integrity guards.

    Thread-safe. Holds lazy references to all 6 specialist guards.
    Provides check_all() for a full financial governance snapshot and
    is_execution_safe() as the unified financial execution gate.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_status_ts: int = 0
        self._status_interval_ns: int = 60 * 1_000_000_000  # 60 seconds

        self._exposure_guard: ExposureGuard | None = None
        self._leverage_monitor: LeverageMonitor | None = None
        self._liquidation_sentinel: LiquidationSentinel | None = None
        self._execution_hazard: ExecutionHazardDetector | None = None
        self._capital_throttle: CapitalThrottle | None = None
        self._kill_switch: KillSwitch | None = None

    # ------------------------------------------------------------------
    # Guard properties
    # ------------------------------------------------------------------

    @property
    def exposure_guard(self) -> ExposureGuard:
        if self._exposure_guard is None:
            self._exposure_guard = get_exposure_guard()
        return self._exposure_guard

    @property
    def leverage_monitor(self) -> LeverageMonitor:
        if self._leverage_monitor is None:
            self._leverage_monitor = get_leverage_monitor()
        return self._leverage_monitor

    @property
    def liquidation_sentinel(self) -> LiquidationSentinel:
        if self._liquidation_sentinel is None:
            self._liquidation_sentinel = get_liquidation_sentinel()
        return self._liquidation_sentinel

    @property
    def execution_hazard(self) -> ExecutionHazardDetector:
        if self._execution_hazard is None:
            self._execution_hazard = get_execution_hazard_detector()
        return self._execution_hazard

    @property
    def capital_throttle(self) -> CapitalThrottle:
        if self._capital_throttle is None:
            self._capital_throttle = get_capital_throttle()
        return self._capital_throttle

    @property
    def kill_switch(self) -> KillSwitch:
        if self._kill_switch is None:
            self._kill_switch = get_kill_switch()
        return self._kill_switch

    # ------------------------------------------------------------------
    # Execution gate
    # ------------------------------------------------------------------

    def is_execution_safe(self, adapter_id: str = "") -> bool:
        """
        Return True only when all financial guards allow execution.

        Checks:
          1. Kill switch is not active
          2. Capital throttle is not triggered
          3. No execution hazard blocks the adapter
        """
        if self.kill_switch.is_active():
            return False
        throttle = self.capital_throttle.check_throttle()
        if throttle.throttled:
            return False
        if adapter_id and self.execution_hazard.is_blocked(adapter_id):
            return False
        return True

    # ------------------------------------------------------------------
    # Unified health check
    # ------------------------------------------------------------------

    def check_all(self) -> FinancialGovernanceStatus:
        """
        Aggregate financial governance health snapshot.
        """
        ts_ns = _time.time_ns()

        kill_state = self.kill_switch.state()
        kill_switch_safe = kill_state is KillSwitchState.SAFE

        exposure_ok = self.exposure_guard.violation_count() == 0
        leverage_ok = self.leverage_monitor.violation_count() == 0
        liquidation_safe = len(self.liquidation_sentinel.at_risk_positions()) == 0
        execution_hazard_free = not self.execution_hazard.any_blocked()
        capital_throttle_ok = not self.capital_throttle.check_throttle().throttled
        total_exposure_usd = self.exposure_guard.total_exposure_usd()

        active_violations = (
            self.exposure_guard.violation_count()
            + self.leverage_monitor.violation_count()
            + self.liquidation_sentinel.violation_count()
            + self.execution_hazard.violation_count()
            + self.capital_throttle.throttle_count()
            + self.kill_switch.arm_count()
        )

        overall_healthy = (
            kill_switch_safe
            and exposure_ok
            and leverage_ok
            and liquidation_safe
            and execution_hazard_free
            and capital_throttle_ok
        )

        detail_parts: list[str] = []
        if not kill_switch_safe:
            detail_parts.append(f"kill_switch={kill_state.value}")
        if not exposure_ok:
            detail_parts.append(
                f"exposure_violations={self.exposure_guard.violation_count()}"
            )
        if not leverage_ok:
            detail_parts.append(
                f"leverage_violations={self.leverage_monitor.violation_count()}"
            )
        if not liquidation_safe:
            detail_parts.append(
                f"at_risk_positions={len(self.liquidation_sentinel.at_risk_positions())}"
            )
        if not execution_hazard_free:
            detail_parts.append("execution_hazard_active")
        if not capital_throttle_ok:
            detail_parts.append("capital_throttled")
        detail = "; ".join(detail_parts) if detail_parts else "all guards healthy"

        return FinancialGovernanceStatus(
            ts_ns=ts_ns,
            overall_healthy=overall_healthy,
            exposure_ok=exposure_ok,
            leverage_ok=leverage_ok,
            liquidation_safe=liquidation_safe,
            execution_hazard_free=execution_hazard_free,
            capital_throttle_ok=capital_throttle_ok,
            kill_switch_state=kill_state,
            active_violations=active_violations,
            total_exposure_usd=total_exposure_usd,
            detail=detail,
        )

    # ------------------------------------------------------------------
    # Periodic status emission
    # ------------------------------------------------------------------

    def emit_status(self) -> FinancialGovernanceStatus:
        """
        Compute and emit FINGOV_STATUS to the governance ledger.

        Rate-limited to once per _status_interval_ns.
        """
        ts_ns = _time.time_ns()
        status = self.check_all()

        with self._lock:
            should_emit = (ts_ns - self._last_status_ts) >= self._status_interval_ns
            if should_emit:
                self._last_status_ts = ts_ns

        if should_emit:
            append_event(
                "GOVERNANCE",
                "FINGOV_STATUS",
                "financial_governance.engine",
                {
                    "overall_healthy": status.overall_healthy,
                    "exposure_ok": status.exposure_ok,
                    "leverage_ok": status.leverage_ok,
                    "liquidation_safe": status.liquidation_safe,
                    "execution_hazard_free": status.execution_hazard_free,
                    "capital_throttle_ok": status.capital_throttle_ok,
                    "kill_switch_state": status.kill_switch_state.value,
                    "active_violations": status.active_violations,
                    "total_exposure_usd": status.total_exposure_usd,
                    "detail": status.detail,
                },
            )

        return status

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        status = self.check_all()
        return {
            "status": {
                "overall_healthy": status.overall_healthy,
                "exposure_ok": status.exposure_ok,
                "leverage_ok": status.leverage_ok,
                "liquidation_safe": status.liquidation_safe,
                "execution_hazard_free": status.execution_hazard_free,
                "capital_throttle_ok": status.capital_throttle_ok,
                "kill_switch_state": status.kill_switch_state.value,
                "active_violations": status.active_violations,
                "total_exposure_usd": status.total_exposure_usd,
            },
            "exposure": self.exposure_guard.snapshot(),
            "leverage": self.leverage_monitor.snapshot(),
            "liquidation": self.liquidation_sentinel.snapshot(),
            "execution_hazard": self.execution_hazard.snapshot(),
            "capital_throttle": self.capital_throttle.snapshot(),
            "kill_switch": self.kill_switch.snapshot(),
        }


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: FinancialGovernanceEngine | None = None
_lock = threading.Lock()


def get_financial_governance() -> FinancialGovernanceEngine:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = FinancialGovernanceEngine()
    return _instance


__all__ = ["FinancialGovernanceEngine", "get_financial_governance"]

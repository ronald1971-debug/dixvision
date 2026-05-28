"""
core/contracts/financial_governance.py
DIX VISION v42.2 — Financial Governance contract types.

Financial governance becomes fully active once live execution begins.
During development phases it validates simulation realism, exposure model
correctness, and execution hazard detection before real capital is at risk.

Priority in the architecture:
  - Development phases: P4 (lowest) — cognitive integrity comes first
  - Live deployment:    P2 (co-equal with operator sovereignty)

Protections formalised here:
  1. Exposure Guard         — net exposure within declared risk budgets
  2. Leverage Monitor       — leverage bounds never exceeded
  3. Liquidation Sentinel   — liquidation distance early warning
  4. Execution Hazard       — execution path hazard detection
  5. Capital Throttle       — capital deployment rate limiting
  6. Kill Switch            — financial-layer emergency halt
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class FinancialViolationKind(StrEnum):
    EXPOSURE_BREACH         = "EXPOSURE_BREACH"         # net exposure > budget
    LEVERAGE_EXCEEDED       = "LEVERAGE_EXCEEDED"        # leverage > configured max
    LIQUIDATION_IMMINENT    = "LIQUIDATION_IMMINENT"     # within liquidation buffer
    EXECUTION_HAZARD        = "EXECUTION_HAZARD"         # adapter/routing failure risk
    CAPITAL_RATE_EXCEEDED   = "CAPITAL_RATE_EXCEEDED"    # capital deployment too fast
    SLIPPAGE_EXCESSIVE      = "SLIPPAGE_EXCESSIVE"       # realised slippage > model
    DRAWDOWN_LIMIT          = "DRAWDOWN_LIMIT"           # daily/session drawdown breached
    EXCHANGE_UNRELIABLE     = "EXCHANGE_UNRELIABLE"      # venue circuit-breaker open


class FinancialSeverity(StrEnum):
    INFO     = "INFO"
    WARNING  = "WARNING"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


class KillSwitchState(StrEnum):
    ARMED    = "ARMED"      # kill switch activated
    SAFE     = "SAFE"       # normal operation
    COOLDOWN = "COOLDOWN"   # post-kill cooldown (no re-arm until operator clears)


@dataclass(frozen=True, slots=True)
class ExposureViolation:
    """Net exposure breach record."""
    ts_ns: int
    asset_class: str
    symbol: str
    current_exposure_usd: float
    budget_usd: float
    overage_usd: float
    severity: FinancialSeverity
    detail: str = ""


@dataclass(frozen=True, slots=True)
class LeverageBreach:
    """Leverage limit breach record."""
    ts_ns: int
    symbol: str
    venue: str
    current_leverage: float
    max_leverage: float
    severity: FinancialSeverity
    detail: str = ""


@dataclass(frozen=True, slots=True)
class LiquidationRiskRecord:
    """Liquidation proximity early warning."""
    ts_ns: int
    position_id: str
    symbol: str
    venue: str
    mark_price: float
    liquidation_price: float
    distance_pct: float         # (mark - liq) / mark × 100
    warning_threshold_pct: float
    severity: FinancialSeverity
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ExecutionHazardRecord:
    """Execution path hazard detection record."""
    ts_ns: int
    adapter_id: str
    hazard_kind: FinancialViolationKind
    description: str
    severity: FinancialSeverity
    auto_blocked: bool = False  # whether the hazard automatically blocked the order
    detail: str = ""


@dataclass(frozen=True, slots=True)
class CapitalThrottleStatus:
    """Capital deployment rate throttle status."""
    ts_ns: int
    window_ns: int              # rolling window used
    deployed_usd: float         # capital deployed in window
    limit_usd: float            # limit for this window
    utilisation: float          # 0.0 = idle … 1.0 = at limit
    throttled: bool             # True = new deployments blocked
    detail: str = ""


@dataclass(frozen=True, slots=True)
class KillSwitchRecord:
    """Financial kill switch state record."""
    ts_ns: int
    state: KillSwitchState
    reason: str
    trigger: str                # "operator" | "auto_drawdown" | "auto_exposure"
    positions_closed: int = 0
    orders_cancelled: int = 0


@dataclass(frozen=True, slots=True)
class FinancialGovernanceStatus:
    """Aggregate snapshot of all financial governance guards."""
    ts_ns: int
    overall_healthy: bool
    exposure_ok: bool
    leverage_ok: bool
    liquidation_safe: bool
    execution_hazard_free: bool
    capital_throttle_ok: bool
    kill_switch_state: KillSwitchState
    active_violations: int
    total_exposure_usd: float = 0.0
    detail: str = ""


__all__ = [
    "FinancialViolationKind",
    "FinancialSeverity",
    "KillSwitchState",
    "ExposureViolation",
    "LeverageBreach",
    "LiquidationRiskRecord",
    "ExecutionHazardRecord",
    "CapitalThrottleStatus",
    "KillSwitchRecord",
    "FinancialGovernanceStatus",
]

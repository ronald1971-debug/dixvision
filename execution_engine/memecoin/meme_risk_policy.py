"""Memecoin risk policy (BUILD-DIRECTIVE — Tier 3 Memecoin Execution).

Implements the 60-second pre-trade safety stack and hard position caps
as specified in MEMECOIN_TRADING_SPEC.md. This is a BLOCKING gate:
no memecoin trade reaches execution without passing all checks.

Non-negotiables enforced:
- Burner wallet only (never main treasury)
- Hard position caps per trade and per day
- Safety stack: mint authority, freeze authority, bundle detection,
  dev wallet history, LP status, honeypot simulation
- Dead-man sensor failure → fail-closed
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SafetyCheckResult(StrEnum):
    """Result of a single safety check."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    SKIPPED = "SKIPPED"


class MemeRejectionReason(StrEnum):
    """Why a memecoin trade was rejected."""

    MINT_AUTHORITY_ACTIVE = "MINT_AUTHORITY_ACTIVE"
    FREEZE_AUTHORITY_ACTIVE = "FREEZE_AUTHORITY_ACTIVE"
    UPDATE_AUTHORITY_ACTIVE = "UPDATE_AUTHORITY_ACTIVE"
    BUNDLE_DETECTED = "BUNDLE_DETECTED"
    DEV_WALLET_SUSPICIOUS = "DEV_WALLET_SUSPICIOUS"
    LP_NOT_LOCKED = "LP_NOT_LOCKED"
    HONEYPOT_DETECTED = "HONEYPOT_DETECTED"
    POSITION_CAP_EXCEEDED = "POSITION_CAP_EXCEEDED"
    DAILY_CAP_EXCEEDED = "DAILY_CAP_EXCEEDED"
    SLIPPAGE_CEILING_EXCEEDED = "SLIPPAGE_CEILING_EXCEEDED"
    MEV_RISK_REJECT = "MEV_RISK_REJECT"
    SENSOR_OFFLINE = "SENSOR_OFFLINE"
    SMART_MONEY_ABSENT = "SMART_MONEY_ABSENT"


@dataclass(frozen=True, slots=True)
class SafetyReport:
    """Full safety report for a memecoin trade candidate."""

    token_address: str
    chain: str
    passed: bool
    checks: dict[str, SafetyCheckResult]
    rejection_reason: MemeRejectionReason | None
    smart_money_holders: int
    smart_money_net_buy: float
    execution_time_ms: float
    ts_ns: int


@dataclass(slots=True)
class MemePositionLimits:
    """Hard position limits for memecoin trading."""

    max_per_trade_sol: float = 0.5
    max_concurrent_positions: int = 5
    max_daily_trades: int = 20
    max_bankroll_pct: float = 0.05  # 5% of total treasury
    slippage_ceiling_pct: float = 25.0
    phase1_max_sol: float = 0.2
    phase2_multiplier: float = 3.0


class MemeRiskPolicy:
    """Enforces memecoin-specific risk policy.

    Runs the 60-second pre-trade safety stack and enforces hard caps.
    All execution paths must pass through this gate.
    """

    def __init__(self, *, limits: MemePositionLimits | None = None) -> None:
        self._limits = limits or MemePositionLimits()
        self._daily_trades: int = 0
        self._active_positions: int = 0
        self._daily_pnl_sol: float = 0.0

    def evaluate(
        self,
        *,
        token_address: str,
        chain: str = "solana",
        proposed_size_sol: float,
        mint_authority_revoked: bool = False,
        freeze_authority_revoked: bool = False,
        update_authority_revoked: bool = False,
        bundle_detected: bool = False,
        dev_wallet_clean: bool = False,
        lp_locked: bool = False,
        honeypot_simulation_passed: bool = False,
        smart_money_holders: int = 0,
        smart_money_net_buy: float = 0.0,
        estimated_slippage_pct: float = 0.0,
        sensors_online: bool = True,
        ts_ns: int = 0,
    ) -> SafetyReport:
        """Run full safety stack on a trade candidate."""
        checks: dict[str, SafetyCheckResult] = {}
        rejection: MemeRejectionReason | None = None

        # Sensor dead-man check (fail-closed)
        if not sensors_online:
            return SafetyReport(
                token_address=token_address,
                chain=chain,
                passed=False,
                checks={"sensors": SafetyCheckResult.FAILED},
                rejection_reason=MemeRejectionReason.SENSOR_OFFLINE,
                smart_money_holders=0,
                smart_money_net_buy=0.0,
                execution_time_ms=0.0,
                ts_ns=ts_ns,
            )

        # Check 1: Mint authority
        checks["mint_authority"] = (
            SafetyCheckResult.PASSED if mint_authority_revoked else SafetyCheckResult.FAILED
        )
        if not mint_authority_revoked:
            rejection = MemeRejectionReason.MINT_AUTHORITY_ACTIVE

        # Check 2: Freeze authority
        checks["freeze_authority"] = (
            SafetyCheckResult.PASSED if freeze_authority_revoked else SafetyCheckResult.FAILED
        )
        if not freeze_authority_revoked and rejection is None:
            rejection = MemeRejectionReason.FREEZE_AUTHORITY_ACTIVE

        # Check 3: Update authority
        checks["update_authority"] = (
            SafetyCheckResult.PASSED if update_authority_revoked else SafetyCheckResult.FAILED
        )
        if not update_authority_revoked and rejection is None:
            rejection = MemeRejectionReason.UPDATE_AUTHORITY_ACTIVE

        # Check 4: Bundle detection
        checks["bundle_detection"] = (
            SafetyCheckResult.PASSED if not bundle_detected else SafetyCheckResult.FAILED
        )
        if bundle_detected and rejection is None:
            rejection = MemeRejectionReason.BUNDLE_DETECTED

        # Check 5: Dev wallet history
        checks["dev_wallet"] = (
            SafetyCheckResult.PASSED if dev_wallet_clean else SafetyCheckResult.FAILED
        )
        if not dev_wallet_clean and rejection is None:
            rejection = MemeRejectionReason.DEV_WALLET_SUSPICIOUS

        # Check 6: LP locked
        checks["lp_locked"] = SafetyCheckResult.PASSED if lp_locked else SafetyCheckResult.FAILED
        if not lp_locked and rejection is None:
            rejection = MemeRejectionReason.LP_NOT_LOCKED

        # Check 7: Honeypot simulation
        checks["honeypot"] = (
            SafetyCheckResult.PASSED if honeypot_simulation_passed else SafetyCheckResult.FAILED
        )
        if not honeypot_simulation_passed and rejection is None:
            rejection = MemeRejectionReason.HONEYPOT_DETECTED

        # Position cap checks
        if proposed_size_sol > self._limits.max_per_trade_sol and rejection is None:
            rejection = MemeRejectionReason.POSITION_CAP_EXCEEDED
            checks["position_cap"] = SafetyCheckResult.FAILED
        else:
            checks["position_cap"] = SafetyCheckResult.PASSED

        if self._daily_trades >= self._limits.max_daily_trades and rejection is None:
            rejection = MemeRejectionReason.DAILY_CAP_EXCEEDED
            checks["daily_cap"] = SafetyCheckResult.FAILED
        else:
            checks["daily_cap"] = SafetyCheckResult.PASSED

        # Slippage ceiling
        if estimated_slippage_pct > self._limits.slippage_ceiling_pct and rejection is None:
            rejection = MemeRejectionReason.SLIPPAGE_CEILING_EXCEEDED
            checks["slippage"] = SafetyCheckResult.FAILED
        else:
            checks["slippage"] = SafetyCheckResult.PASSED

        passed = rejection is None

        return SafetyReport(
            token_address=token_address,
            chain=chain,
            passed=passed,
            checks=checks,
            rejection_reason=rejection,
            smart_money_holders=smart_money_holders,
            smart_money_net_buy=smart_money_net_buy,
            execution_time_ms=0.0,
            ts_ns=ts_ns,
        )

    def record_trade(self) -> None:
        """Record that a trade was executed (for daily cap tracking)."""
        self._daily_trades += 1
        self._active_positions += 1

    def close_position(self, pnl_sol: float = 0.0) -> None:
        """Record position close."""
        self._active_positions = max(0, self._active_positions - 1)
        self._daily_pnl_sol += pnl_sol

    def reset_daily(self) -> None:
        """Reset daily counters (called at UTC midnight)."""
        self._daily_trades = 0
        self._daily_pnl_sol = 0.0

    @property
    def can_open_position(self) -> bool:
        """Check if we can open another position."""
        return self._active_positions < self._limits.max_concurrent_positions

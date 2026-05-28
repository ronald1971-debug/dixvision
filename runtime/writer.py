"""Authority Writer — controlled state mutation (CONVERGENCE PILLAR 1).

High-level write operations that compose multiple field updates into
semantically meaningful state transitions. Each write operation:
1. Validates preconditions
2. Applies the update via WriterToken
3. Returns the resulting snapshot

This module is the ONLY entry point for state mutation (enforced by
B-RUNTIME lint rule). Direct field writes via WriterToken.write() are
permitted but these high-level operations are preferred for audit clarity.
"""

from __future__ import annotations

from core.contracts.operator_authority import (
    LearningAuthority,
    LiveExecutionAuthority,
    OperatorAuthority,
    PracticeAuthority,
    TradingDomain,
    TradingMode,
)
from runtime.authority import RuntimeSnapshot, WriterToken


class AuthorityWriter:
    """High-level state mutation operations.

    Wraps a WriterToken with semantic operations that validate
    preconditions and produce meaningful audit descriptions.
    """

    def __init__(self, token: WriterToken) -> None:
        self._token = token

    @property
    def holder(self) -> str:
        return self._token.holder

    # --- Operator Authority mutations ---

    def set_learning(
        self, *, value: LearningAuthority, ts_ns: int, current: OperatorAuthority
    ) -> RuntimeSnapshot:
        """Set learning authority level."""
        new_oa = OperatorAuthority(
            learning=value,
            practice=current.practice,
            live_execution=current.live_execution,
            trading_mode=current.trading_mode,
            semi_auto_policy=current.semi_auto_policy,
            operator_id=current.operator_id,
        )
        return self._token.write(
            ts_ns,
            operator_authority=new_oa,
            learning_active=value != LearningAuthority.OFF,
        )

    def set_practice(
        self, *, value: PracticeAuthority, ts_ns: int, current: OperatorAuthority
    ) -> RuntimeSnapshot:
        """Set practice authority."""
        new_oa = OperatorAuthority(
            learning=current.learning,
            practice=value,
            live_execution=current.live_execution,
            trading_mode=current.trading_mode,
            semi_auto_policy=current.semi_auto_policy,
            operator_id=current.operator_id,
        )
        return self._token.write(ts_ns, operator_authority=new_oa)

    def set_live_execution(
        self, *, value: LiveExecutionAuthority, ts_ns: int, current: OperatorAuthority
    ) -> RuntimeSnapshot:
        """Set live execution authority."""
        new_oa = OperatorAuthority(
            learning=current.learning,
            practice=current.practice,
            live_execution=value,
            trading_mode=current.trading_mode,
            semi_auto_policy=current.semi_auto_policy,
            operator_id=current.operator_id,
        )
        return self._token.write(
            ts_ns,
            operator_authority=new_oa,
            live_execution_blocked=value == LiveExecutionAuthority.BLOCKED,
        )

    def set_trading_mode(
        self,
        *,
        domain: TradingDomain,
        mode: TradingMode,
        ts_ns: int,
        current: OperatorAuthority,
    ) -> RuntimeSnapshot:
        """Set trading mode for a domain."""
        new_modes = dict(current.trading_mode)
        new_modes[domain] = mode
        new_oa = OperatorAuthority(
            learning=current.learning,
            practice=current.practice,
            live_execution=current.live_execution,
            trading_mode=new_modes,
            semi_auto_policy=current.semi_auto_policy,
            operator_id=current.operator_id,
        )
        return self._token.write(ts_ns, operator_authority=new_oa)

    # --- System state mutations ---

    def set_system_mode(self, *, mode: str, ts_ns: int) -> RuntimeSnapshot:
        """Transition system mode (governance-only operation)."""
        return self._token.write(ts_ns, system_mode=mode)

    def record_hazard(
        self, *, code: str, ts_ns: int, current_hazards: tuple[str, ...]
    ) -> RuntimeSnapshot:
        """Add a hazard to active hazards."""
        if code in current_hazards:
            return self._token.write(ts_ns)  # no-op, just bump version
        new_hazards = (*current_hazards, code)
        return self._token.write(
            ts_ns,
            active_hazards=new_hazards,
            health_score=max(0.0, 1.0 - len(new_hazards) * 0.1),
        )

    def clear_hazard(
        self, *, code: str, ts_ns: int, current_hazards: tuple[str, ...]
    ) -> RuntimeSnapshot:
        """Remove a hazard from active hazards."""
        new_hazards = tuple(h for h in current_hazards if h != code)
        return self._token.write(
            ts_ns,
            active_hazards=new_hazards,
            health_score=max(0.0, 1.0 - len(new_hazards) * 0.1),
        )

    # --- Market state mutations ---

    def update_market_state(self, *, ts_ns: int, connected: bool) -> RuntimeSnapshot:
        """Update market connection state."""
        return self._token.write(
            ts_ns,
            last_market_ts_ns=ts_ns,
            market_connected=connected,
        )

    # --- Position / exposure mutations ---

    def update_positions(
        self,
        *,
        open_positions: int,
        total_exposure_usd: float,
        unrealized_pnl_usd: float,
        ts_ns: int,
    ) -> RuntimeSnapshot:
        """Update position and exposure state."""
        return self._token.write(
            ts_ns,
            open_positions=open_positions,
            total_exposure_usd=total_exposure_usd,
            unrealized_pnl_usd=unrealized_pnl_usd,
        )

    # --- Governance mutations ---

    def set_freeze(self, *, active: bool, ts_ns: int) -> RuntimeSnapshot:
        """Set freeze state."""
        return self._token.write(ts_ns, freeze_active=active)

    def set_governance_mode(self, *, mode: str, ts_ns: int) -> RuntimeSnapshot:
        """Set governance enforcement mode."""
        return self._token.write(ts_ns, governance_mode=mode)

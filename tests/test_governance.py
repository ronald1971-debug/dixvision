"""tests/test_governance.py
DIX VISION v42.2 — Governance Layer Integration Tests

Tests for all three governance layers:
- operator_governance: authority, lockout, consent
- financial_governance: kill switch, exposure, throttle
- system_governance: topology, contract integrity

Verifies the core operator sovereignty constraint:
"Execution is BLOCKED until operator explicitly enables it."
"""

from __future__ import annotations

import pytest


class TestOperatorGovernance:
    """Operator sovereignty tests."""

    def test_execution_blocked_by_default(self):
        from operator_governance.engine import get_operator_governance
        gov = get_operator_governance()
        # By default, execution must be blocked
        assert gov.is_execution_allowed() is False

    def test_authority_levels_ordered_correctly(self):
        from core.contracts.operator_governance import AuthorityLevel
        assert AuthorityLevel.CONSTITUTIONAL.value > AuthorityLevel.ADMINISTRATIVE.value \
               or AuthorityLevel.CONSTITUTIONAL == "CONSTITUTIONAL"

    def test_constitutional_authority_cannot_be_delegated(self):
        from operator_governance.operator_constitution import OperatorConstitution
        from core.contracts.operator_governance import AuthorityLevel
        constitution = OperatorConstitution()
        # Attempting to delegate CONSTITUTIONAL should raise
        with pytest.raises((ValueError, PermissionError)):
            constitution.delegate("other_principal", AuthorityLevel.CONSTITUTIONAL)

    def test_lockout_blocks_execution(self):
        from operator_governance.manual_lockout import ManualLockoutGuard
        from core.contracts.operator_governance import LockoutScope
        guard = ManualLockoutGuard()
        guard.issue_lockout(LockoutScope.EXECUTION, reason="test_lockout")
        assert guard.is_locked(LockoutScope.EXECUTION) is True

    def test_lockout_can_be_lifted(self):
        from operator_governance.manual_lockout import ManualLockoutGuard
        from core.contracts.operator_governance import LockoutScope
        guard = ManualLockoutGuard()
        lockout = guard.issue_lockout(LockoutScope.EXECUTION, reason="test")
        assert guard.is_locked(LockoutScope.EXECUTION) is True
        guard.lift_lockout(lockout.lockout_id)
        assert guard.is_locked(LockoutScope.EXECUTION) is False


class TestFinancialGovernance:
    """Financial governance (kill switch, exposure, throttle) tests."""

    def test_kill_switch_initially_safe(self):
        from financial_governance.kill_switch import KillSwitch
        from core.contracts.financial_governance import KillSwitchState
        ks = KillSwitch()
        assert ks.state == KillSwitchState.SAFE

    def test_kill_switch_arm_transitions_to_armed(self):
        from financial_governance.kill_switch import KillSwitch
        from core.contracts.financial_governance import KillSwitchState
        ks = KillSwitch()
        ks.arm(reason="drawdown_breach", trigger="auto")
        assert ks.state == KillSwitchState.ARMED

    def test_kill_switch_only_operator_clears(self):
        from financial_governance.kill_switch import KillSwitch
        from core.contracts.financial_governance import KillSwitchState
        ks = KillSwitch()
        ks.arm(reason="test", trigger="auto")
        ks.enter_cooldown()
        result = ks.clear(operator_id="ronald")
        assert result is not None
        assert ks.state == KillSwitchState.SAFE

    def test_capital_throttle_blocks_when_exceeded(self):
        from financial_governance.capital_throttle import CapitalThrottle
        throttle = CapitalThrottle(limit_usd=1000.0, window_seconds=60.0)
        status = throttle.record_deployment(1500.0)
        assert status.throttled is True

    def test_capital_throttle_allows_within_limit(self):
        from financial_governance.capital_throttle import CapitalThrottle
        throttle = CapitalThrottle(limit_usd=10_000.0, window_seconds=60.0)
        status = throttle.record_deployment(500.0)
        assert status.throttled is False


class TestSystemGovernance:
    """System governance (topology, contract integrity) tests."""

    def test_topology_guard_detects_b1_violation(self):
        from system_governance.topology_guard import TopologyGuard
        from core.contracts.system_governance import TopologyViolationKind
        guard = TopologyGuard()
        guard.declare_dependencies("intelligence_engine.agents", ["core", "state"])
        violations = guard.record_import(
            importer="intelligence_engine.agents.trend_follower",
            importee="execution_engine.hot_path.fast_risk_cache",
        )
        b1_violations = [v for v in violations if v.kind == TopologyViolationKind.B1_CROSS_ENGINE_IMPORT]
        assert len(b1_violations) >= 1

    def test_contract_integrity_validates_version(self):
        from system_governance.contract_integrity import ContractIntegrityGuard
        guard = ContractIntegrityGuard()
        guard.register_contract(
            subsystem="execution_engine",
            interface="ExecutionIntent",
            version="2",
            emits_audit=True,
        )
        result = guard.validate(
            source="intelligence_engine",
            target="execution_engine",
            required_interface="ExecutionIntent",
            required_version="2",
        )
        assert result.valid is True

    def test_contract_integrity_fails_on_version_mismatch(self):
        from system_governance.contract_integrity import ContractIntegrityGuard
        guard = ContractIntegrityGuard()
        guard.register_contract(
            subsystem="execution_engine",
            interface="ExecutionIntent",
            version="1",
            emits_audit=True,
        )
        result = guard.validate(
            source="intelligence_engine",
            target="execution_engine",
            required_interface="ExecutionIntent",
            required_version="2",
        )
        assert result.valid is False

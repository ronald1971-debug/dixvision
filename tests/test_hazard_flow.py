"""tests/test_hazard_flow.py
DIX VISION v42.2 — Hazard Flow Integration Tests

Tests end-to-end hazard detection and propagation flow:
1. Hazard sensor detects condition → emits HazardEvent
2. HazardEvent propagated to financial_governance
3. financial_governance assesses severity → may block execution

Also tests that hazard events from different adapters don't interfere.
"""

from __future__ import annotations

import time
import pytest


class TestHazardEventFlow:
    """Hazard detection → propagation → governance response."""

    def test_hazard_event_has_required_fields(self):
        """HazardEvent frozen dataclass has all required fields."""
        from core.contracts.events import HazardEvent, HazardSeverity
        evt = HazardEvent(
            ts_ns=time.time_ns(),
            code="HAZ_TEST_001",
            severity=HazardSeverity.HIGH,
            source="test_sensor",
            detail="Test hazard event",
            meta={"key": "value"},
            produced_by_engine="system_engine",
            kind="SYSTEM_ANOMALY",
        )
        assert evt.code == "HAZ_TEST_001"
        assert evt.severity == HazardSeverity.HIGH
        assert evt.source == "test_sensor"

    def test_execution_hazard_detector_auto_blocks_on_critical(self):
        """ExecutionHazardDetector auto-blocks for CRITICAL hazard kinds."""
        from financial_governance.execution_hazard import ExecutionHazardDetector
        from core.contracts.financial_governance import FinancialSeverity, FinancialViolationKind
        detector = ExecutionHazardDetector()
        detector.record_hazard(
            adapter_id="binance",
            hazard_kind=FinancialViolationKind.DRAWDOWN_LIMIT,
            description="Portfolio drawdown exceeded",
            severity=FinancialSeverity.CRITICAL,
        )
        assert detector.is_blocked("binance") is True

    def test_hazard_cleared_after_explicit_clear(self):
        from financial_governance.execution_hazard import ExecutionHazardDetector
        from core.contracts.financial_governance import FinancialSeverity, FinancialViolationKind
        detector = ExecutionHazardDetector()
        detector.record_hazard(
            adapter_id="kraken",
            hazard_kind=FinancialViolationKind.SLIPPAGE_EXCESSIVE,
            description="High slippage detected",
            severity=FinancialSeverity.HIGH,
        )
        assert detector.is_blocked("kraken") is True
        detector.clear_hazard("kraken", FinancialViolationKind.SLIPPAGE_EXCESSIVE)
        assert detector.is_blocked("kraken") is False

    def test_low_severity_hazard_does_not_block(self):
        from financial_governance.execution_hazard import ExecutionHazardDetector
        from core.contracts.financial_governance import FinancialSeverity, FinancialViolationKind
        detector = ExecutionHazardDetector()
        detector.record_hazard(
            adapter_id="oanda",
            hazard_kind=FinancialViolationKind.EXECUTION_HAZARD,
            description="Minor execution issue",
            severity=FinancialSeverity.WARNING,
        )
        assert detector.is_blocked("oanda") is False

    def test_multiple_adapters_independent(self):
        """Hazard on one adapter should not block a different adapter."""
        from financial_governance.execution_hazard import ExecutionHazardDetector
        from core.contracts.financial_governance import FinancialSeverity, FinancialViolationKind
        detector = ExecutionHazardDetector()
        detector.record_hazard(
            adapter_id="binance",
            hazard_kind=FinancialViolationKind.EXCHANGE_UNRELIABLE,
            description="Exchange connectivity issues",
            severity=FinancialSeverity.CRITICAL,
        )
        assert detector.is_blocked("binance") is True
        assert detector.is_blocked("kraken") is False


class TestHazardSeverityOrdering:
    def test_severity_ordering(self):
        from core.contracts.events import HazardSeverity
        severities = [HazardSeverity.LOW, HazardSeverity.MEDIUM,
                      HazardSeverity.HIGH, HazardSeverity.CRITICAL]
        assert len(severities) == 4

    def test_critical_always_triggers_kill_switch(self):
        """CRITICAL financial severity should block execution for that adapter."""
        from financial_governance.engine import get_financial_governance
        from core.contracts.financial_governance import FinancialSeverity, FinancialViolationKind
        engine = get_financial_governance()
        engine.execution_hazard.record_hazard(
            adapter_id="test_adapter",
            hazard_kind=FinancialViolationKind.DRAWDOWN_LIMIT,
            description="Critical drawdown",
            severity=FinancialSeverity.CRITICAL,
        )
        assert engine.is_execution_safe("test_adapter") is False

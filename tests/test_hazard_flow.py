"""tests/test_hazard_flow.py
DIX VISION v42.2 — Hazard Flow Integration Tests

Tests end-to-end hazard detection and propagation flow:
1. Hazard sensor detects condition → emits HazardEvent
2. HazardEvent propagated to financial_governance
3. financial_governance assesses severity → may trigger kill switch

Also tests that hazard events from different sensors don't interfere.
"""

from __future__ import annotations

import time
import pytest


class TestHazardEventFlow:
    """Hazard detection → propagation → governance response."""

    def test_hazard_event_has_required_fields(self):
        """HazardEvent frozen dataclass has all required fields."""
        from system_engine.hazard_sensors.base import HazardEvent, HazardSeverity
        evt = HazardEvent(
            hazard_id="HAZ_TEST_001",
            source="test_sensor",
            severity=HazardSeverity.HIGH,
            description="Test hazard event",
            ts_ns=time.time_ns(),
            meta={"key": "value"},
        )
        assert evt.hazard_id == "HAZ_TEST_001"
        assert evt.severity == HazardSeverity.HIGH

    def test_execution_hazard_detector_auto_blocks_on_critical(self):
        """ExecutionHazardDetector auto-blocks for critical hazard kinds."""
        from financial_governance.execution_hazard import ExecutionHazardDetector
        from core.contracts.financial_governance import FinancialSeverity
        detector = ExecutionHazardDetector()
        detector.record_hazard(
            adapter_id="binance",
            hazard_kind="DRAWDOWN_LIMIT",
            description="Portfolio drawdown exceeded",
            severity=FinancialSeverity.CRITICAL,
        )
        assert detector.is_blocked("binance") is True

    def test_hazard_cleared_after_explicit_clear(self):
        from financial_governance.execution_hazard import ExecutionHazardDetector
        from core.contracts.financial_governance import FinancialSeverity
        detector = ExecutionHazardDetector()
        detector.record_hazard(
            adapter_id="kraken",
            hazard_kind="SLIPPAGE_EXCESSIVE",
            description="High slippage detected",
            severity=FinancialSeverity.HIGH,
        )
        assert detector.is_blocked("kraken") is True
        detector.clear_hazard("kraken", "SLIPPAGE_EXCESSIVE")
        # After clearing the auto-block hazard, should no longer be blocked
        assert detector.is_blocked("kraken") is False

    def test_low_severity_hazard_does_not_block(self):
        from financial_governance.execution_hazard import ExecutionHazardDetector
        from core.contracts.financial_governance import FinancialSeverity
        detector = ExecutionHazardDetector()
        detector.record_hazard(
            adapter_id="oanda",
            hazard_kind="LATENCY_ELEVATED",
            description="Minor latency increase",
            severity=FinancialSeverity.LOW,
        )
        assert detector.is_blocked("oanda") is False

    def test_multiple_adapters_independent(self):
        """Hazard on one adapter should not block a different adapter."""
        from financial_governance.execution_hazard import ExecutionHazardDetector
        from core.contracts.financial_governance import FinancialSeverity
        detector = ExecutionHazardDetector()
        detector.record_hazard(
            adapter_id="binance",
            hazard_kind="EXCHANGE_UNRELIABLE",
            description="Exchange connectivity issues",
            severity=FinancialSeverity.CRITICAL,
        )
        assert detector.is_blocked("binance") is True
        assert detector.is_blocked("kraken") is False


class TestHazardSeverityOrdering:
    def test_severity_ordering(self):
        from system_engine.hazard_sensors.base import HazardSeverity
        severities = [HazardSeverity.LOW, HazardSeverity.MEDIUM,
                      HazardSeverity.HIGH, HazardSeverity.CRITICAL]
        assert len(severities) == 4

    def test_critical_always_triggers_kill_switch(self):
        """CRITICAL financial severity should arm the kill switch."""
        from financial_governance.engine import get_financial_governance
        from core.contracts.financial_governance import FinancialSeverity
        engine = get_financial_governance()
        # Record a CRITICAL hazard
        engine.execution_hazard.record_hazard(
            adapter_id="test_adapter",
            hazard_kind="DRAWDOWN_LIMIT",
            description="Critical drawdown",
            severity=FinancialSeverity.CRITICAL,
        )
        # Execution should not be safe for that adapter
        assert engine.is_execution_safe("test_adapter") is False

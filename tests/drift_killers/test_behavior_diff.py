"""Drift killer — behavior diff regression guard.

Catches silent behavioural regressions by asserting fixed numeric
outputs for known inputs. Update golden values only via deliberate PR.
"""

from __future__ import annotations

import math


class TestBehaviorDiff:
    """Golden-value regression tests for core pure-computation modules."""

    def test_impact_model_golden(self) -> None:
        from execution_engine.strategic_execution.market_impact.model import ImpactModel

        model = ImpactModel(sigma_bps=50.0, temp_fraction=0.6, scale=1.0)
        est = model.estimate(symbol="BTC", ts_ns=0, qty=100.0, adv=10_000.0)
        # sqrt(100/10000) * 50 = sqrt(0.01) * 50 = 0.1 * 50 = 5.0 bps total
        assert abs(est.total_bps - 5.0) < 1e-9
        assert abs(est.temporary_bps - 3.0) < 1e-9
        assert abs(est.permanent_bps - 2.0) < 1e-9

    def test_twap_plan_slice_count(self) -> None:
        from execution_engine.strategic_execution.optimal_execution import OptimalExecutor

        plan = OptimalExecutor(n_slices=8).plan_twap(
            symbol="ETH", ts_ns=0, total_qty=80.0, adv=800.0, mid_price=3000.0
        )
        assert len(plan.slices) == 8
        assert all(math.isclose(s.qty, 10.0) for s in plan.slices)

    def test_adversarial_market_order_on_high_urgency(self) -> None:
        from execution_engine.strategic_execution.adversarial_executor import AdversarialExecutor

        plan = AdversarialExecutor(aggression_threshold=0.7).plan(
            symbol="SOL", ts_ns=0, side="BUY",
            urgency=0.9, spread_bps=5.0, crowding_score=0.3,
        )
        assert plan.order_type == "MARKET"

    def test_adversarial_limit_order_on_low_urgency(self) -> None:
        from execution_engine.strategic_execution.adversarial_executor import AdversarialExecutor

        plan = AdversarialExecutor(aggression_threshold=0.7).plan(
            symbol="SOL", ts_ns=0, side="SELL",
            urgency=0.2, spread_bps=10.0, crowding_score=0.1,
        )
        assert plan.order_type == "LIMIT"
        assert plan.limit_offset_bps > 0.0

    def test_depth_estimator_imbalance_range(self) -> None:
        from execution_engine.strategic_execution.market_impact.depth_estimator import DepthEstimator

        est = DepthEstimator(depth_bps=20.0)
        snap = est.snapshot(
            symbol="BTC", ts_ns=0, mid_price=50_000.0,
            bids=[(49_990.0, 1.0), (49_950.0, 2.0)],
            asks=[(50_005.0, 0.5), (50_050.0, 0.5)],
        )
        assert -1.0 <= snap.imbalance <= 1.0

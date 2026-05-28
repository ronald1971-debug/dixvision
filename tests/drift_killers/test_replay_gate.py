"""Drift killer — INV-15 byte-identical replay gate.

Verifies that pure-computation modules produce identical outputs
given identical (ts_ns, seed) inputs across multiple runs.
"""

from __future__ import annotations

import hashlib


def _digest(data: bytes) -> str:
    return hashlib.blake2b(data, digest_size=16).hexdigest()


def _encode(obj: object) -> bytes:
    return str(obj).encode()


class TestReplayGate:
    """Replay gate: same inputs → same outputs, two runs."""

    def test_optimal_executor_twap_is_deterministic(self) -> None:
        from execution_engine.strategic_execution.optimal_execution import OptimalExecutor

        executor = OptimalExecutor(n_slices=5)
        kwargs = dict(symbol="BTC-USD", ts_ns=1_700_000_000_000_000_000,
                      total_qty=100.0, adv=1_000.0, mid_price=50_000.0)

        plan_a = executor.plan_twap(**kwargs)
        plan_b = executor.plan_twap(**kwargs)

        assert _digest(_encode(plan_a)) == _digest(_encode(plan_b)), (
            "TWAP plan is not byte-identical across two calls with same inputs"
        )

    def test_impact_model_is_deterministic(self) -> None:
        from execution_engine.strategic_execution.market_impact.model import ImpactModel

        model = ImpactModel(sigma_bps=50.0)
        kwargs = dict(symbol="ETH-USD", ts_ns=1_700_000_000_000_000_001,
                      qty=500.0, adv=10_000.0)

        est_a = model.estimate(**kwargs)
        est_b = model.estimate(**kwargs)

        assert est_a == est_b, "ImpactEstimate is not byte-identical across two calls"

    def test_adversarial_plan_is_deterministic(self) -> None:
        from execution_engine.strategic_execution.adversarial_executor import AdversarialExecutor

        executor = AdversarialExecutor()
        kwargs = dict(symbol="SOL-USD", ts_ns=1_700_000_000_000_000_002,
                      side="BUY", urgency=0.5, spread_bps=8.0, crowding_score=0.4)

        plan_a = executor.plan(**kwargs)
        plan_b = executor.plan(**kwargs)

        assert plan_a == plan_b, "AdversarialPlan is not byte-identical across two calls"

    def test_slippage_curve_predict_is_deterministic(self) -> None:
        from execution_engine.strategic_execution.market_impact.slippage_curve import SlippageCurve

        curve = SlippageCurve()
        curve.add_sample(0.1, 2.5)
        curve.add_sample(0.5, 5.0)
        curve.add_sample(1.0, 8.0)

        pred_a = curve.predict(0.3)
        pred_b = curve.predict(0.3)

        assert pred_a == pred_b, "SlippageCurve.predict is not deterministic"

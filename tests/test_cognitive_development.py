"""Tests for Manifest §6 cognitive pipeline and §7 maturity registry."""

from __future__ import annotations

import time
import unittest

from cognitive_governance.cognitive_maturity import (
    CognitiveMaturityRegistry,
    MaturityStage,
    get_cognitive_maturity_registry,
)
from intelligence_engine.cognitive.cognitive_development_pipeline import (
    CognitiveDevelopmentPipeline,
    CognitiveStage,
    get_cognitive_development_pipeline,
)
from governance.market_context_projector import MarketContextProjector
from intelligence_engine.cognitive.dyon_signal_bridge import DyonSignalBridge


def _ts() -> int:
    return time.time_ns()


class TestCognitiveDevelopmentPipeline(unittest.TestCase):
    def test_stages_are_sequential(self) -> None:
        pipe = CognitiveDevelopmentPipeline()
        self.assertEqual(pipe.stage, CognitiveStage.OBSERVATION)
        seen = [pipe.stage]
        for _ in range(len(CognitiveStage) - 1):
            pipe.tick(ts_ns=_ts())
            seen.append(pipe.stage)
        self.assertEqual(len(seen), len(CognitiveStage))
        self.assertEqual(seen[-1], CognitiveStage.APPROVED_COGNITIVE_UPDATE)

    def test_singleton_snapshot(self) -> None:
        snap = get_cognitive_development_pipeline().snapshot()
        self.assertEqual(snap["pipeline"], "CognitiveDevelopmentPipeline")
        self.assertIn("stage", snap)


class TestCognitiveMaturityRegistry(unittest.TestCase):
    def test_no_skip(self) -> None:
        reg = CognitiveMaturityRegistry(initial=MaturityStage.OBSERVATION)
        bad = reg.propose_advance(
            target=MaturityStage.BELIEF_SYSTEMS,
            ts_ns=_ts(),
            governance_approved=True,
        )
        self.assertFalse(bad["approved"])
        self.assertEqual(bad["reason"], "stage_skip_forbidden")

    def test_governance_required_stage_6_plus(self) -> None:
        reg = CognitiveMaturityRegistry(initial=MaturityStage.CONTINUOUS_LEARNING)
        denied = reg.propose_advance(
            target=MaturityStage.EVOLUTION_PROPOSALS,
            ts_ns=_ts(),
            governance_approved=False,
        )
        self.assertFalse(denied["approved"])
        self.assertEqual(denied["reason"], "governance_approval_required")
        ok = reg.propose_advance(
            target=MaturityStage.EVOLUTION_PROPOSALS,
            ts_ns=_ts(),
            governance_approved=True,
        )
        self.assertTrue(ok["approved"])

    def test_singleton(self) -> None:
        self.assertIs(get_cognitive_maturity_registry(), get_cognitive_maturity_registry())


class TestGovernedMarketContext(unittest.TestCase):
    def test_bridge_subscribes_governed_channel_only(self) -> None:
        bridge = DyonSignalBridge()
        bridge.activate()
        snap = bridge.snapshot()
        self.assertEqual(snap["channel"], "GOVERNED_MARKET_CONTEXT")

    def test_projector_snapshot(self) -> None:
        proj = MarketContextProjector()
        proj.activate()
        snap = proj.snapshot()
        self.assertTrue(snap["subscribed"])


if __name__ == "__main__":
    unittest.main()

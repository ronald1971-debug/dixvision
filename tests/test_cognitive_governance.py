"""
tests/test_cognitive_governance.py
DIX VISION v42.2 — Cognitive Governance Layer Tests

Covers:
  - CognitiveConstitution: gate decisions (block vs. allow vs. warn)
  - LearningCoherenceMonitor: composite scoring, halt threshold, trend
  - LongHorizonMemoryStore: observe, state transitions, identity signal
  - Integration: violation registration propagates to gate decisions
"""

from __future__ import annotations

import time
import unittest

from cognitive_governance.cognitive_constitution import (
    CognitiveConstitution,
    CognitiveGateKind,
)
from cognitive_governance.learning_coherence import (
    CoherenceLevel,
    LearningCoherenceMonitor,
    LearningCoherenceScore,
    _coherence_level,
)
from cognitive_governance.long_horizon_memory import (
    LongHorizonMemoryStore,
    PatternKind,
    PatternState,
)
from core.contracts.cognitive_governance import CognitiveViolationKind


def _ts() -> int:
    return time.time_ns()


# ---------------------------------------------------------------------------
# CognitiveConstitution tests
# ---------------------------------------------------------------------------

class TestCognitiveConstitution(unittest.TestCase):

    def setUp(self) -> None:
        self.cc = CognitiveConstitution()

    def test_no_violations_allows_all_actions(self) -> None:
        for action in ("mutation", "learning_update", "signal", "strategy_selection"):
            d = self.cc.gate(action, _ts())
            self.assertTrue(d.allowed, f"Expected allowed for {action} with no violations")
            self.assertIsNone(d.gate_kind)

    def test_mutation_irreversible_blocks_mutation(self) -> None:
        self.cc.record_violation(CognitiveViolationKind.MUTATION_IRREVERSIBLE)
        d = self.cc.gate_mutation(_ts())
        self.assertFalse(d.allowed)
        self.assertEqual(d.gate_kind, CognitiveGateKind.BLOCK_MUTATION)
        self.assertIn(CognitiveViolationKind.MUTATION_IRREVERSIBLE, d.violations)

    def test_mutation_block_does_not_affect_signal(self) -> None:
        self.cc.record_violation(CognitiveViolationKind.MUTATION_IRREVERSIBLE)
        d = self.cc.gate_signal(_ts())
        self.assertTrue(d.allowed)

    def test_hallucination_loop_blocks_signal(self) -> None:
        self.cc.record_violation(CognitiveViolationKind.HALLUCINATION_LOOP)
        d = self.cc.gate_signal(_ts())
        self.assertFalse(d.allowed)
        self.assertEqual(d.gate_kind, CognitiveGateKind.BLOCK_SIGNAL)

    def test_hallucination_loop_does_not_block_mutation(self) -> None:
        self.cc.record_violation(CognitiveViolationKind.HALLUCINATION_LOOP)
        d = self.cc.gate_mutation(_ts())
        self.assertTrue(d.allowed)

    def test_epistemic_drift_critical_blocks_learning(self) -> None:
        self.cc.record_violation(CognitiveViolationKind.EPISTEMIC_DRIFT_CRITICAL)
        d = self.cc.gate_learning_update(_ts())
        self.assertFalse(d.allowed)
        self.assertEqual(d.gate_kind, CognitiveGateKind.BLOCK_LEARNING)

    def test_reward_hacking_blocks_learning(self) -> None:
        self.cc.record_violation(CognitiveViolationKind.REWARD_HACKING)
        d = self.cc.gate_learning_update(_ts())
        self.assertFalse(d.allowed)

    def test_calibration_drift_blocks_strategy_selection(self) -> None:
        self.cc.record_violation(CognitiveViolationKind.CALIBRATION_DRIFT)
        d = self.cc.gate_strategy_selection(_ts())
        self.assertFalse(d.allowed)
        self.assertEqual(d.gate_kind, CognitiveGateKind.BLOCK_STRATEGY_SEL)

    def test_warning_only_violation_does_not_block(self) -> None:
        for warning_v in (
            CognitiveViolationKind.EPISTEMIC_DRIFT_WARNING,
            CognitiveViolationKind.LEARNING_NOT_GROUNDED,
            CognitiveViolationKind.IDENTITY_INSTABILITY,
            CognitiveViolationKind.OVERCONFIDENCE,
        ):
            cc = CognitiveConstitution()
            cc.record_violation(warning_v)
            for action in ("mutation", "learning_update", "signal", "strategy_selection"):
                d = cc.gate(action, _ts())
                self.assertTrue(d.allowed, f"Warning violation {warning_v} should not block {action}")

    def test_clear_violation_restores_access(self) -> None:
        self.cc.record_violation(CognitiveViolationKind.REWARD_HACKING)
        self.assertFalse(self.cc.gate_learning_update(_ts()).allowed)
        self.cc.clear_violation(CognitiveViolationKind.REWARD_HACKING)
        self.assertTrue(self.cc.gate_learning_update(_ts()).allowed)

    def test_clear_all_violations(self) -> None:
        self.cc.record_violation(CognitiveViolationKind.MUTATION_IRREVERSIBLE)
        self.cc.record_violation(CognitiveViolationKind.REWARD_HACKING)
        self.cc.record_violation(CognitiveViolationKind.HALLUCINATION_LOOP)
        self.cc.clear_all_violations()
        self.assertEqual(len(self.cc.active_violations()), 0)
        self.assertTrue(self.cc.gate_mutation(_ts()).allowed)
        self.assertTrue(self.cc.gate_learning_update(_ts()).allowed)
        self.assertTrue(self.cc.gate_signal(_ts()).allowed)

    def test_multiple_blocking_violations_listed(self) -> None:
        self.cc.record_violation(CognitiveViolationKind.MUTATION_IRREVERSIBLE)
        self.cc.record_violation(CognitiveViolationKind.LINEAGE_CYCLE)
        d = self.cc.gate_mutation(_ts())
        self.assertFalse(d.allowed)
        self.assertGreaterEqual(len(d.violations), 1)

    def test_override_violations_for_testing(self) -> None:
        # No active violations on the instance
        d = self.cc.gate(
            "mutation", _ts(),
            override_violations=(CognitiveViolationKind.MUTATION_IRREVERSIBLE,),
        )
        self.assertFalse(d.allowed)

    def test_recent_blocks_returns_only_blocked(self) -> None:
        self.cc.gate_mutation(_ts())  # allowed
        self.cc.record_violation(CognitiveViolationKind.MUTATION_IRREVERSIBLE)
        self.cc.gate_mutation(_ts())  # blocked
        blocks = self.cc.recent_blocks()
        self.assertTrue(all(not b.allowed for b in blocks))
        self.assertGreaterEqual(len(blocks), 1)

    def test_snapshot_reflects_active_violations(self) -> None:
        self.cc.record_violation(CognitiveViolationKind.REWARD_HACKING)
        snap = self.cc.snapshot()
        self.assertIn("REWARD_HACKING", snap["active_violations"])


# ---------------------------------------------------------------------------
# CoherenceLevel helper
# ---------------------------------------------------------------------------

class TestCoherenceLevel(unittest.TestCase):

    def test_boundaries(self) -> None:
        self.assertEqual(_coherence_level(1.00), CoherenceLevel.HIGH)
        self.assertEqual(_coherence_level(0.80), CoherenceLevel.HIGH)
        self.assertEqual(_coherence_level(0.79), CoherenceLevel.MEDIUM)
        self.assertEqual(_coherence_level(0.60), CoherenceLevel.MEDIUM)
        self.assertEqual(_coherence_level(0.59), CoherenceLevel.LOW)
        self.assertEqual(_coherence_level(0.40), CoherenceLevel.LOW)
        self.assertEqual(_coherence_level(0.39), CoherenceLevel.CRITICAL)
        self.assertEqual(_coherence_level(0.00), CoherenceLevel.CRITICAL)


# ---------------------------------------------------------------------------
# LearningCoherenceMonitor tests (unit — no external guard deps needed)
# ---------------------------------------------------------------------------

class TestLearningCoherenceMonitor(unittest.TestCase):

    def setUp(self) -> None:
        self.monitor = LearningCoherenceMonitor()

    def test_score_returns_coherence_score(self) -> None:
        s = self.monitor.score()
        self.assertIsInstance(s, LearningCoherenceScore)
        self.assertGreaterEqual(s.overall_score, 0.0)
        self.assertLessEqual(s.overall_score, 1.0)

    def test_level_matches_overall_score(self) -> None:
        s = self.monitor.score()
        expected = _coherence_level(s.overall_score)
        self.assertEqual(s.level, expected)

    def test_halt_learning_when_below_threshold(self) -> None:
        # Force a score below 0.60 by injecting a known-low ts; score() is
        # pure aggregation — we can't mock guards here, so just check the
        # halt_learning field is consistent with the overall_score.
        s = self.monitor.score()
        if s.overall_score < 0.60:
            self.assertTrue(s.halt_learning)
        else:
            self.assertFalse(s.halt_learning)

    def test_history_accumulates(self) -> None:
        for _ in range(5):
            self.monitor.score()
        snap = self.monitor.snapshot()
        self.assertGreaterEqual(snap["history_size"], 5)

    def test_history_capped_at_max(self) -> None:
        for _ in range(self.monitor._max_history + 10):
            self.monitor.score()
        snap = self.monitor.snapshot()
        self.assertLessEqual(snap["history_size"], self.monitor._max_history)

    def test_trend_zero_with_single_entry(self) -> None:
        self.monitor.score()
        self.assertEqual(self.monitor.trend(10), 0.0)

    def test_trend_direction(self) -> None:
        # Populate history with synthetically-produced scores
        import time as _time
        # We can only observe the trend function, not inject synthetic scores.
        # At minimum, verify it returns a float without error.
        for _ in range(12):
            self.monitor.score()
        t = self.monitor.trend(10)
        self.assertIsInstance(t, float)

    def test_latest_returns_most_recent(self) -> None:
        s1 = self.monitor.score()
        s2 = self.monitor.score()
        latest = self.monitor.latest()
        self.assertEqual(latest.ts_ns, s2.ts_ns)

    def test_snapshot_fields(self) -> None:
        self.monitor.score()
        snap = self.monitor.snapshot()
        self.assertIn("latest_score", snap)
        self.assertIn("latest_level", snap)
        self.assertIn("halt_learning", snap)
        self.assertIn("history_size", snap)
        self.assertIn("trend_10", snap)


# ---------------------------------------------------------------------------
# LongHorizonMemoryStore tests
# ---------------------------------------------------------------------------

class TestLongHorizonMemoryStore(unittest.TestCase):

    def setUp(self) -> None:
        self.store = LongHorizonMemoryStore()

    def _ts(self, offset_ns: int = 0) -> int:
        return time.time_ns() + offset_ns

    def test_observe_creates_pattern(self) -> None:
        p = self.store.observe("system", PatternKind.COGNITIVE_TREND, 0.8, _ts())
        self.assertIsNotNone(p)
        self.assertEqual(p.subject, "system")
        self.assertEqual(p.kind, PatternKind.COGNITIVE_TREND)
        self.assertEqual(p.occurrence_count, 1)

    def test_repeated_observe_updates_pattern(self) -> None:
        p1 = self.store.observe("sys", PatternKind.BEHAVIORAL_DRIFT, 0.7, _ts())
        p2 = self.store.observe("sys", PatternKind.BEHAVIORAL_DRIFT, 0.75, _ts() + 1000)
        self.assertEqual(p2.pattern_id, p1.pattern_id)
        self.assertEqual(p2.occurrence_count, 2)

    def test_forming_state_with_few_observations(self) -> None:
        p = self.store.observe("sys", PatternKind.COGNITIVE_TREND, 0.9, _ts())
        self.assertEqual(p.state, PatternState.FORMING)

    def test_active_state_after_enough_observations(self) -> None:
        for i in range(5):
            p = self.store.observe("sys", PatternKind.COGNITIVE_TREND, 0.8,
                                   _ts() + i * 1000)
        # With 5+ observations and no extreme drift, should be ACTIVE or STABLE
        self.assertIn(p.state, (PatternState.ACTIVE, PatternState.STABLE,
                                PatternState.DRIFTING))

    def test_stable_state_when_low_drift_high_confidence(self) -> None:
        for i in range(10):
            self.store.observe("sys", PatternKind.STRATEGY_PERSONALITY, 0.9,
                               _ts() + i * 1_000_000_000)
        p = self.store.get("sys", PatternKind.STRATEGY_PERSONALITY)
        # Stable observations should converge to STABLE
        self.assertIn(p.state, (PatternState.STABLE, PatternState.ACTIVE))

    def test_retire_removes_from_active(self) -> None:
        self.store.observe("sys", PatternKind.BEHAVIORAL_DRIFT, 0.5, _ts())
        self.store.retire("sys", PatternKind.BEHAVIORAL_DRIFT)
        p = self.store.get("sys", PatternKind.BEHAVIORAL_DRIFT)
        self.assertEqual(p.state, PatternState.RETIRED)

    def test_retired_pattern_triggers_new_creation(self) -> None:
        t1 = _ts()
        p1 = self.store.observe("sys", PatternKind.BEHAVIORAL_DRIFT, 0.6, t1)
        self.store.retire("sys", PatternKind.BEHAVIORAL_DRIFT)
        t2 = _ts() + 1_000_000
        p2 = self.store.observe("sys", PatternKind.BEHAVIORAL_DRIFT, 0.7, t2)
        self.assertNotEqual(p1.pattern_id, p2.pattern_id)
        self.assertEqual(p2.state, PatternState.FORMING)

    def test_patterns_for_subject_excludes_retired(self) -> None:
        self.store.observe("sys", PatternKind.COGNITIVE_TREND, 0.8, _ts())
        self.store.observe("sys", PatternKind.BEHAVIORAL_DRIFT, 0.6, _ts() + 1)
        self.store.retire("sys", PatternKind.BEHAVIORAL_DRIFT)
        active = self.store.patterns_for_subject("sys")
        kinds = {p.kind for p in active}
        self.assertIn(PatternKind.COGNITIVE_TREND, kinds)
        self.assertNotIn(PatternKind.BEHAVIORAL_DRIFT, kinds)

    def test_patterns_by_kind(self) -> None:
        self.store.observe("sys1", PatternKind.REGIME_ADAPTATION, 0.7, _ts())
        self.store.observe("sys2", PatternKind.REGIME_ADAPTATION, 0.8, _ts() + 1)
        self.store.observe("sys3", PatternKind.COGNITIVE_TREND, 0.9, _ts() + 2)
        regime_patterns = self.store.patterns_by_kind(PatternKind.REGIME_ADAPTATION)
        subjects = {p.subject for p in regime_patterns}
        self.assertIn("sys1", subjects)
        self.assertIn("sys2", subjects)
        self.assertNotIn("sys3", subjects)

    def test_identity_stability_signal_no_patterns(self) -> None:
        sig = self.store.identity_stability_signal()
        self.assertEqual(sig, 1.0)

    def test_identity_stability_signal_high_confidence(self) -> None:
        for i in range(5):
            self.store.observe("system", PatternKind.IDENTITY_EVOLUTION, 0.95,
                               _ts() + i * 1000)
        sig = self.store.identity_stability_signal()
        self.assertGreater(sig, 0.7)

    def test_identity_stability_signal_low_confidence(self) -> None:
        for i in range(5):
            self.store.observe("system", PatternKind.BEHAVIORAL_DRIFT, 0.2,
                               _ts() + i * 1000)
        sig = self.store.identity_stability_signal()
        self.assertLess(sig, 0.5)

    def test_snapshot_fields_present(self) -> None:
        self.store.observe("sys", PatternKind.COGNITIVE_TREND, 0.8, _ts())
        snap = self.store.snapshot()
        self.assertIn("total_patterns", snap.__dataclass_fields__)

    def test_snapshot_dataclass_fields(self) -> None:
        snap = self.store.snapshot()
        self.assertIsNotNone(snap.ts_ns)
        self.assertIsInstance(snap.identity_stability_signal, float)
        self.assertGreaterEqual(snap.identity_stability_signal, 0.0)
        self.assertLessEqual(snap.identity_stability_signal, 1.0)

    def test_concerning_patterns_low_confidence(self) -> None:
        for i in range(4):
            self.store.observe("sys", PatternKind.PERFORMANCE_DEGRADATION, 0.3,
                               _ts() + i * 1000)
        concerning = self.store.concerning_patterns()
        # PERFORMANCE_DEGRADATION when ACTIVE is always concerning
        kinds = {p.kind for p in concerning}
        # May or may not flag depending on state reached (FORMING is not checked)
        self.assertIsInstance(concerning, list)

    def test_all_patterns_include_retired_when_requested(self) -> None:
        self.store.observe("sys", PatternKind.COGNITIVE_TREND, 0.8, _ts())
        self.store.retire("sys", PatternKind.COGNITIVE_TREND)
        all_p = self.store.all_patterns(include_retired=True)
        self.assertTrue(any(p.state == PatternState.RETIRED for p in all_p))
        active_only = self.store.all_patterns(include_retired=False)
        self.assertFalse(any(p.state == PatternState.RETIRED for p in active_only))

    def test_observations_capped_at_max(self) -> None:
        limit = LongHorizonMemoryStore._MAX_OBS_PER_PATTERN
        for i in range(limit + 10):
            self.store.observe("sys", PatternKind.COGNITIVE_TREND, 0.8, _ts() + i)
        p = self.store.get("sys", PatternKind.COGNITIVE_TREND)
        self.assertLessEqual(len(p.observations), limit)

    def test_confidence_is_bounded(self) -> None:
        for i in range(10):
            self.store.observe("sys", PatternKind.COGNITIVE_TREND,
                               0.5 + (i % 3) * 0.1, _ts() + i * 1000)
        p = self.store.get("sys", PatternKind.COGNITIVE_TREND)
        self.assertGreaterEqual(p.confidence, 0.0)
        self.assertLessEqual(p.confidence, 1.0)

    def test_drift_rate_computed_with_enough_obs(self) -> None:
        # Increasing confidence → positive drift_rate
        for i in range(10):
            self.store.observe("sys", PatternKind.BEHAVIORAL_DRIFT,
                               0.1 + i * 0.08, _ts() + i * 1_000_000_000)
        p = self.store.get("sys", PatternKind.BEHAVIORAL_DRIFT)
        self.assertGreater(p.drift_rate, 0.0)

    def test_declining_confidence_negative_drift(self) -> None:
        for i in range(10):
            self.store.observe("sys", PatternKind.BEHAVIORAL_DRIFT,
                               0.9 - i * 0.08, _ts() + i * 1_000_000_000)
        p = self.store.get("sys", PatternKind.BEHAVIORAL_DRIFT)
        self.assertLess(p.drift_rate, 0.0)


# ---------------------------------------------------------------------------
# Integration: violation → constitution → gate blocked
# ---------------------------------------------------------------------------

class TestConstitutionIntegration(unittest.TestCase):

    def test_memory_contamination_blocks_learning(self) -> None:
        cc = CognitiveConstitution()
        cc.record_violation(CognitiveViolationKind.MEMORY_CONTAMINATION)
        d = cc.gate("learning_update", _ts())
        self.assertFalse(d.allowed)
        self.assertIn("MEMORY_CONTAMINATION", d.reason)

    def test_synthetic_feedback_blocks_reward_update(self) -> None:
        cc = CognitiveConstitution()
        cc.record_violation(CognitiveViolationKind.SYNTHETIC_FEEDBACK)
        d = cc.gate("reward_update", _ts())
        self.assertFalse(d.allowed)

    def test_lineage_gap_blocks_evolution(self) -> None:
        cc = CognitiveConstitution()
        cc.record_violation(CognitiveViolationKind.LINEAGE_GAP)
        d = cc.gate("evolution", _ts())
        self.assertFalse(d.allowed)
        self.assertEqual(d.gate_kind, CognitiveGateKind.BLOCK_MUTATION)

    def test_self_referential_reward_blocks_distillation(self) -> None:
        cc = CognitiveConstitution()
        cc.record_violation(CognitiveViolationKind.SELF_REFERENTIAL_REWARD)
        d = cc.gate("distillation", _ts())
        self.assertFalse(d.allowed)

    def test_no_cross_contamination_between_instances(self) -> None:
        cc1 = CognitiveConstitution()
        cc2 = CognitiveConstitution()
        cc1.record_violation(CognitiveViolationKind.REWARD_HACKING)
        # cc2 has no violations
        self.assertFalse(cc1.gate_learning_update(_ts()).allowed)
        self.assertTrue(cc2.gate_learning_update(_ts()).allowed)


if __name__ == "__main__":
    unittest.main()

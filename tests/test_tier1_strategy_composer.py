"""Tests for Tier 1 strategy composer modules."""

from intelligence_engine.strategy_composer.composition_validator import (
    CompositionValidator,
    ValidationResult,
)
from intelligence_engine.strategy_composer.regime_fitness import (
    RegimeFitnessTracker,
)


def test_regime_fitness_update():
    tracker = RegimeFitnessTracker(ema_alpha=0.2)
    for i in range(10):
        score = tracker.update(
            entity_id="atom_1",
            regime="TRENDING",
            outcome=0.5,
            ts_ns=i * 1000,
        )
    assert score.score > 0.5
    assert score.sample_size == 10
    assert score.confidence > 0.5


def test_regime_fitness_different_regimes():
    tracker = RegimeFitnessTracker()
    for i in range(10):
        tracker.update(entity_id="a1", regime="TRENDING", outcome=0.8, ts_ns=i)
    for i in range(10):
        tracker.update(entity_id="a1", regime="CRISIS", outcome=-0.3, ts_ns=i + 100)
    trending = tracker.get_fitness("a1", "TRENDING")
    crisis = tracker.get_fitness("a1", "CRISIS")
    assert trending is not None
    assert crisis is not None
    assert trending.score > crisis.score


def test_regime_fitness_top_for_regime():
    tracker = RegimeFitnessTracker()
    for i in range(10):
        tracker.update(entity_id="good_atom", regime="VOLATILE", outcome=0.7, ts_ns=i)
        tracker.update(entity_id="bad_atom", regime="VOLATILE", outcome=-0.3, ts_ns=i)
    top = tracker.get_top_for_regime("VOLATILE", top_n=5)
    assert len(top) >= 1
    assert top[0].entity_id == "good_atom"


def test_cross_regime_robustness():
    tracker = RegimeFitnessTracker()
    for regime in ["TRENDING", "VOLATILE", "CRISIS", "RANGING"]:
        for i in range(10):
            tracker.update(entity_id="generalist", regime=regime, outcome=0.3, ts_ns=i)
    robustness = tracker.cross_regime_robustness("generalist")
    assert robustness > 0.5  # should be robust (similar across regimes)


def test_composition_validator_valid():
    v = CompositionValidator(min_atoms=2, min_sources=2)
    report = v.validate(
        strategy_id="strat_1",
        atom_categories=["ENTRY", "EXIT", "RISK", "TIMING"],
        source_traders=["ptj", "soros", "seykota"],
        diversity_score=0.7,
    )
    assert report.result == ValidationResult.VALID
    assert report.score == 1.0


def test_composition_validator_missing_exit():
    v = CompositionValidator()
    report = v.validate(
        strategy_id="strat_2",
        atom_categories=["ENTRY", "ENTRY", "RISK"],
        source_traders=["ptj", "soros"],
        diversity_score=0.6,
    )
    assert report.result == ValidationResult.REJECTED_MISSING_EXIT
    assert "has_exit" in report.checks_failed


def test_composition_validator_single_source():
    v = CompositionValidator(min_sources=2)
    report = v.validate(
        strategy_id="strat_3",
        atom_categories=["ENTRY", "EXIT", "RISK"],
        source_traders=["ptj", "ptj", "ptj"],
        diversity_score=0.8,
    )
    assert report.result == ValidationResult.REJECTED_SINGLE_SOURCE


def test_composition_validator_high_correlation():
    v = CompositionValidator(max_correlation=0.85)
    report = v.validate(
        strategy_id="strat_4",
        atom_categories=["ENTRY", "EXIT", "RISK"],
        source_traders=["ptj", "soros"],
        pairwise_correlations=[0.95],
        diversity_score=0.8,
    )
    assert report.result == ValidationResult.REJECTED_EXCESSIVE_CORRELATION

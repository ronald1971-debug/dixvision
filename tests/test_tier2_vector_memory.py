"""Tests for Tier 2 vector memory and trader abstraction modules."""

from learning_engine.trader_abstraction.normalizer import TraderAbstractionNormalizer
from learning_engine.trader_abstraction.pattern_encoder import PatternEncoder
from learning_engine.trader_abstraction.philosophy_encoder import PhilosophyEmbeddingEncoder
from learning_engine.vector_memory.market_regime_embeddings import (
    MarketRegimeEmbeddingStore,
    RegimeEmbedding,
)
from learning_engine.vector_memory.narrative_embeddings import (
    NarrativeEmbedding,
    NarrativeEmbeddingStore,
)


def test_narrative_embedding_store():
    store = NarrativeEmbeddingStore(dimension=8)
    emb = NarrativeEmbedding(
        narrative_id="n1",
        theme="btc_halving",
        vector=(0.5, 0.3, 0.8, 0.1, 0.0, 0.0, 0.0, 0.0),
        strength=0.7,
        source_count=5,
        ts_ns=1000,
    )
    store.insert(emb)
    assert store.size == 1

    results = store.search((0.5, 0.3, 0.8, 0.1, 0.0, 0.0, 0.0, 0.0))
    assert len(results) == 1
    assert results[0][1] > 0.9  # high similarity


def test_narrative_dominant():
    store = NarrativeEmbeddingStore(dimension=4)
    store.insert(NarrativeEmbedding("n1", "risk_off", (1, 0, 0, 0), 0.8, 3, 100))
    store.insert(NarrativeEmbedding("n2", "btc_bull", (0, 1, 0, 0), 0.3, 2, 100))
    dominant = store.get_dominant_theme()
    assert dominant is not None
    assert dominant.theme == "risk_off"


def test_regime_embedding_classify():
    store = MarketRegimeEmbeddingStore(dimension=4)
    store.register_regime(
        RegimeEmbedding(
            "r1",
            "TRENDING_BULL",
            (1.0, 0.5, 0.0, 0.0),
            0.3,
            0.8,
            0.5,
            0.7,
            1000,
        )
    )
    store.register_regime(
        RegimeEmbedding(
            "r2",
            "CRISIS",
            (0.0, 0.0, 1.0, 0.9),
            2.0,
            -0.5,
            0.9,
            0.2,
            1000,
        )
    )
    results = store.classify((0.9, 0.4, 0.1, 0.0), top_k=2)
    assert results[0][0].label == "TRENDING_BULL"


def test_regime_transition_detection():
    store = MarketRegimeEmbeddingStore(dimension=4)
    store.register_regime(
        RegimeEmbedding(
            "r1",
            "TRENDING_BULL",
            (1.0, 0.5, 0.0, 0.0),
            0.3,
            0.8,
            0.5,
            0.7,
            0,
        )
    )
    store.register_regime(
        RegimeEmbedding(
            "r2",
            "CRISIS",
            (0.0, 0.0, 1.0, 0.9),
            2.0,
            -0.5,
            0.9,
            0.2,
            0,
        )
    )
    transition = store.detect_transition(
        previous_vector=(1.0, 0.5, 0.0, 0.0),
        current_vector=(0.0, 0.0, 1.0, 0.9),
        threshold=0.3,
        ts_ns=2000,
    )
    assert transition is not None
    assert transition.from_regime == "TRENDING_BULL"
    assert transition.to_regime == "CRISIS"


def test_pattern_encoder():
    encoder = PatternEncoder(dimension=32)
    encoded = encoder.encode(
        pattern_id="p1",
        trader_id="ptj",
        pattern_type="ENTRY",
        success_rate=0.75,
        frequency=20,
        applicable_regimes=["TRENDING_BULL", "VOLATILE"],
        conditions={"rsi": 30.0, "volume": 2.5},
    )
    assert len(encoded.embedding) == 32
    assert encoded.quality_score > 0.5


def test_philosophy_encoder():
    encoder = PhilosophyEmbeddingEncoder(dimension=48)
    emb = encoder.encode(
        trader_id="soros",
        risk_tolerance=0.7,
        time_horizon=0.6,
        systematic_score=0.3,
        conviction_style=0.8,
        market_models=["macro", "event_driven"],
        domain_weights={"forex": 0.5, "equities": 0.3, "commodities": 0.2},
    )
    assert len(emb.embedding) == 48
    assert emb.risk_dimension == 0.7


def test_normalizer():
    norm = TraderAbstractionNormalizer()
    result = norm.normalize(
        trader_id="buffett",
        raw_data={
            "risk_tolerance": "low",
            "time_horizon": "investor",
            "systematic": False,
            "domain_weights": {"equities": 0.8, "fixed_income": 0.2},
            "market_models": ["value"],
            "track_record_years": 50,
        },
    )
    assert result.risk_tolerance == 0.2
    assert result.time_horizon == 0.9
    assert result.systematic_score == 0.0
    assert abs(sum(result.domain_weights.values()) - 1.0) < 0.01

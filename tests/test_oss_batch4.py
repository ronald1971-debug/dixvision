"""Tests for OSS integration batch 4 — Haystack, PyTorch Lightning."""

from integrations.haystack_adapter.rag import (
    DocumentType,
    HaystackRAGAdapter,
)
from integrations.lightning_adapter.trainer import (
    LightningTrainerAdapter,
    ModelType,
    TrainerConfig,
    TrainingStatus,
)

# --- Haystack RAG Tests ---


def test_haystack_add_document():
    adapter = HaystackRAGAdapter()
    doc_id = adapter.add_document(
        "Bitcoin breaks above $70k resistance with strong volume",
        doc_type=DocumentType.MARKET_REPORT,
        metadata={"symbol": "BTC", "source": "analyst"},
    )
    assert doc_id.startswith("doc_")
    assert adapter.document_count == 1


def test_haystack_search():
    adapter = HaystackRAGAdapter()
    adapter.add_document(
        "Bitcoin surges past resistance amid bullish momentum",
        doc_type=DocumentType.MARKET_REPORT,
    )
    adapter.add_document(
        "Ethereum DeFi total value locked hits new highs",
        doc_type=DocumentType.RESEARCH_PAPER,
    )
    adapter.add_document(
        "Federal Reserve signals rate cuts for Q4",
        doc_type=DocumentType.MACRO_BRIEF,
    )

    results = adapter.search("Bitcoin momentum")
    assert len(results) > 0
    assert "bitcoin" in results[0].content.lower() or "momentum" in results[0].content.lower()


def test_haystack_search_by_type():
    adapter = HaystackRAGAdapter()
    adapter.add_document("BTC analysis", doc_type=DocumentType.MARKET_REPORT)
    adapter.add_document("ETH research", doc_type=DocumentType.RESEARCH_PAPER)
    adapter.add_document("SOL report", doc_type=DocumentType.MARKET_REPORT)

    results = adapter.search("analysis", doc_type=DocumentType.MARKET_REPORT)
    assert all(r.doc_type == DocumentType.MARKET_REPORT for r in results)


def test_haystack_rag_query():
    adapter = HaystackRAGAdapter()
    adapter.add_document(
        "The RSI breakout strategy works best in trending markets with strong momentum",
        doc_type=DocumentType.STRATEGY_THESIS,
    )
    adapter.add_document(
        "Mean reversion strategies perform well in range-bound regimes",
        doc_type=DocumentType.STRATEGY_THESIS,
    )

    result = adapter.query("What strategy works in trending markets?")
    assert result.answer != ""
    assert result.query == "What strategy works in trending markets?"
    assert result.generation_ms >= 0


def test_haystack_analyze_document():
    adapter = HaystackRAGAdapter()
    doc_id = adapter.add_document(
        "Bitcoin shows bullish momentum with a clear breakout above resistance. "
        "Strong accumulation detected near support levels.",
        doc_type=DocumentType.MARKET_REPORT,
    )

    analysis = adapter.analyze_document(doc_id)
    assert analysis is not None
    assert "breakout" in analysis.key_signals
    assert "accumulation" in analysis.key_signals
    assert analysis.sentiment > 0  # "bullish" keyword


def test_haystack_bulk_add():
    adapter = HaystackRAGAdapter()
    docs = [
        {"content": f"Document {i} about trading", "doc_type": "research_paper"} for i in range(10)
    ]
    count = adapter.add_documents(docs)
    assert count == 10
    assert adapter.document_count == 10


def test_haystack_delete_document():
    adapter = HaystackRAGAdapter()
    doc_id = adapter.add_document("test content", doc_type=DocumentType.NEWS_ARTICLE)
    assert adapter.document_count == 1

    result = adapter.delete_document(doc_id)
    assert result is True
    assert adapter.document_count == 0


def test_haystack_count_by_type():
    adapter = HaystackRAGAdapter()
    adapter.add_document("a", doc_type=DocumentType.MARKET_REPORT)
    adapter.add_document("b", doc_type=DocumentType.MARKET_REPORT)
    adapter.add_document("c", doc_type=DocumentType.STRATEGY_THESIS)

    assert adapter.count_by_type(DocumentType.MARKET_REPORT) == 2
    assert adapter.count_by_type(DocumentType.STRATEGY_THESIS) == 1


# --- PyTorch Lightning Tests ---


def test_lightning_start_training():
    adapter = LightningTrainerAdapter()
    run_id = adapter.start_training(ModelType.REGIME_CLASSIFIER)

    run = adapter.get_run(run_id)
    assert run is not None
    assert run.model_type == ModelType.REGIME_CLASSIFIER
    assert run.status in (TrainingStatus.COMPLETED, TrainingStatus.STOPPED_EARLY)
    assert len(run.metrics_history) > 0


def test_lightning_early_stopping():
    adapter = LightningTrainerAdapter()
    config = TrainerConfig(max_epochs=100, early_stopping_patience=5)

    run_id = adapter.start_training(
        ModelType.SIGNAL_PREDICTOR,
        config=config,
    )
    run = adapter.get_run(run_id)
    assert run is not None
    # Should stop early (loss plateaus in simulation)
    assert len(run.metrics_history) < 100


def test_lightning_checkpoints():
    adapter = LightningTrainerAdapter()
    config = TrainerConfig(max_epochs=20, checkpoint_every_n_epochs=2)

    run_id = adapter.start_training(ModelType.ALPHA_MINER, config=config)
    run = adapter.get_run(run_id)
    assert run is not None
    assert len(run.checkpoints) > 0

    best = adapter.get_best_checkpoint(run_id)
    assert best is not None
    assert best.val_loss < 1.0  # checkpoint has a reasonable loss


def test_lightning_metrics_tracking():
    adapter = LightningTrainerAdapter()
    run_id = adapter.start_training(ModelType.RISK_ESTIMATOR)

    run = adapter.get_run(run_id)
    assert run is not None
    assert run.best_val_loss < 1.0
    assert run.best_epoch >= 0

    # Loss should decrease over time
    first_loss = run.metrics_history[0].train_loss
    last_loss = run.metrics_history[-1].train_loss
    assert last_loss < first_loss


def test_lightning_compare_runs():
    adapter = LightningTrainerAdapter()
    rid1 = adapter.start_training(ModelType.REGIME_CLASSIFIER)
    rid2 = adapter.start_training(
        ModelType.REGIME_CLASSIFIER,
        config=TrainerConfig(learning_rate=0.01),
    )

    comparison = adapter.compare_runs([rid1, rid2])
    assert rid1 in comparison
    assert rid2 in comparison
    assert "best_val_loss" in comparison[rid1]


def test_lightning_list_runs():
    adapter = LightningTrainerAdapter()
    adapter.start_training(ModelType.REGIME_CLASSIFIER)
    adapter.start_training(ModelType.SIGNAL_PREDICTOR)
    adapter.start_training(ModelType.REGIME_CLASSIFIER)

    all_runs = adapter.list_runs()
    assert len(all_runs) == 3

    regime_only = adapter.list_runs(model_type=ModelType.REGIME_CLASSIFIER)
    assert len(regime_only) == 2

"""Tests for OSS integration batch 3 — Kafka/Redpanda, Ray, OpenBB."""

from integrations.kafka_adapter.streaming import (
    KafkaStreamingAdapter,
    Topic,
)
from integrations.openbb_adapter.financial_data import (
    DataDomain,
    OpenBBFinancialDataAdapter,
)
from integrations.ray_adapter.compute import (
    ComputeMode,
    RayComputeAdapter,
    TaskStatus,
)

# --- Kafka/Redpanda Tests ---


def test_kafka_produce_consume():
    adapter = KafkaStreamingAdapter()
    adapter.connect()

    msg = adapter.produce(Topic.SIGNALS, key="sig_1", value={"confidence": 0.9})
    assert msg.topic == Topic.SIGNALS
    assert msg.key == "sig_1"
    assert msg.value["confidence"] == 0.9

    adapter.subscribe([Topic.SIGNALS])
    # Offset was set to latest on subscribe (after the produce), so consume returns empty
    # Reset offset manually for test
    adapter._consumer_offsets[f"dixvision-main:{Topic.SIGNALS}"] = 0
    messages = adapter.consume(Topic.SIGNALS, max_messages=10)
    assert len(messages) == 1
    assert messages[0].key == "sig_1"


def test_kafka_publish_market_event():
    adapter = KafkaStreamingAdapter()
    adapter.connect()

    msg = adapter.publish_market_event(
        symbol="BTC",
        event_type="tick",
        data={"price": 67000.0, "volume": 1.5},
    )
    assert msg.topic == "dix.market.BTC"
    assert msg.value["price"] == 67000.0


def test_kafka_publish_signal():
    adapter = KafkaStreamingAdapter()
    adapter.connect()

    msg = adapter.publish_signal(
        signal_id="s1",
        symbol="ETH/USDT",
        side="buy",
        confidence=0.85,
    )
    assert msg.value["symbol"] == "ETH/USDT"
    assert msg.value["confidence"] == 0.85


def test_kafka_topic_management():
    adapter = KafkaStreamingAdapter()
    adapter.connect()

    adapter.create_topic("dix.custom.test", partitions=3)
    topics = adapter.list_topics()
    assert "dix.custom.test" in topics


def test_kafka_multiple_messages():
    adapter = KafkaStreamingAdapter()
    adapter.connect()

    for i in range(5):
        adapter.produce(
            Topic.EXECUTION,
            key=f"order_{i}",
            value={"status": "filled"},
        )

    assert adapter.topic_size(Topic.EXECUTION) == 5
    assert adapter.total_messages >= 5


# --- Ray Compute Tests ---


def test_ray_submit_task():
    adapter = RayComputeAdapter()
    adapter.initialize()

    def square(x):
        return x * x

    task_id = adapter.submit_task(square, 7)
    result = adapter.get_task(task_id)
    assert result is not None
    assert result.status == TaskStatus.COMPLETED
    assert result.result == 49


def test_ray_parallel_map():
    adapter = RayComputeAdapter()
    adapter.initialize()

    def double(x):
        return x * 2

    results = adapter.parallel_map(double, [1, 2, 3, 4, 5])
    assert len(results) == 5
    assert all(r.status == TaskStatus.COMPLETED for r in results)
    assert [r.result for r in results] == [2, 4, 6, 8, 10]


def test_ray_task_failure():
    adapter = RayComputeAdapter()
    adapter.initialize()

    def fail(x):
        raise ValueError("boom")

    task_id = adapter.submit_task(fail, 1)
    result = adapter.get_task(task_id)
    assert result is not None
    assert result.status == TaskStatus.FAILED
    assert "boom" in result.error


def test_ray_compute_mode():
    adapter = RayComputeAdapter()
    adapter.initialize()
    assert adapter.compute_mode == ComputeMode.LOCAL


def test_ray_task_counting():
    adapter = RayComputeAdapter()
    adapter.initialize()

    adapter.submit_task(lambda: 1)
    adapter.submit_task(lambda: 2)
    adapter.submit_task(lambda: 3)

    assert adapter.total_tasks == 3
    assert adapter.active_tasks == 0  # all completed


# --- OpenBB Tests ---


def test_openbb_connect_fallback():
    adapter = OpenBBFinancialDataAdapter()
    result = adapter.connect()
    assert result is True  # should always succeed (fallback mode)


def test_openbb_supported_domains():
    adapter = OpenBBFinancialDataAdapter()
    domains = adapter.supported_domains
    assert DataDomain.ECONOMY in domains
    assert DataDomain.CRYPTO in domains
    assert DataDomain.NEWS in domains
    assert len(domains) == 6


def test_openbb_fetch_empty_when_unavailable():
    adapter = OpenBBFinancialDataAdapter()
    adapter.connect()

    # Should return empty lists when OpenBB not installed
    gdp = adapter.fetch_gdp()
    assert gdp == []

    cpi = adapter.fetch_cpi()
    assert cpi == []

    news = adapter.fetch_news(symbols=["BTC"])
    assert news == []


def test_openbb_equity_price_fallback():
    adapter = OpenBBFinancialDataAdapter()
    adapter.connect()

    prices = adapter.fetch_equity_price("AAPL", interval="1d")
    assert prices == []


def test_openbb_crypto_fallback():
    adapter = OpenBBFinancialDataAdapter()
    adapter.connect()

    prices = adapter.fetch_crypto_price("BTC-USD")
    assert prices == []

    metrics = adapter.fetch_crypto_metrics("BTC")
    assert metrics is None

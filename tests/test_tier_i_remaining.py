"""Tests for remaining Tier I items: I-16, I-33, I-37, I-39."""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# I-16 — Binance WebSocket User Data Stream
# ---------------------------------------------------------------------------


class TestBinanceUserDataStream:
    """I-16: Binance WebSocket user data stream adapter."""

    def test_import(self):
        from execution_engine.adapters.binance_ws import (  # noqa: F401
            BalanceUpdate,
            BinanceUserDataStream,
            StreamEvent,
            StreamEventKind,
        )

    def test_connect_in_memory(self):
        from execution_engine.adapters.binance_ws import BinanceUserDataStream

        stream = BinanceUserDataStream(in_memory=True)
        assert not stream.connected
        stream.connect()
        assert stream.connected

    def test_disconnect(self):
        from execution_engine.adapters.binance_ws import BinanceUserDataStream

        stream = BinanceUserDataStream(in_memory=True)
        stream.connect()
        stream.disconnect()
        assert not stream.connected

    def test_inject_mock_event(self):
        from execution_engine.adapters.binance_ws import (
            BinanceUserDataStream,
            StreamEvent,
            StreamEventKind,
        )

        stream = BinanceUserDataStream(in_memory=True)
        stream.connect()
        event = StreamEvent(
            kind=StreamEventKind.EXECUTION_REPORT,
            timestamp_ns=100,
            symbol="BTCUSDT",
            order_id="12345",
            side="BUY",
            status="FILLED",
            filled_qty=0.5,
            price=42000.0,
        )
        stream.inject_mock_event(event)
        assert len(stream.event_log) == 1
        assert stream.event_log[0].symbol == "BTCUSDT"

    def test_inject_mock_balance(self):
        from execution_engine.adapters.binance_ws import (
            BalanceUpdate,
            BinanceUserDataStream,
        )

        stream = BinanceUserDataStream(in_memory=True)
        stream.connect()
        update = BalanceUpdate(asset="BTC", free=1.5, locked=0.2, timestamp_ns=200)
        stream.inject_mock_balance(update)
        assert len(stream.balance_log) == 1
        assert stream.balance_log[0].asset == "BTC"

    def test_callback_on_event(self):
        from execution_engine.adapters.binance_ws import (
            BinanceUserDataStream,
            StreamEvent,
            StreamEventKind,
        )

        received = []
        stream = BinanceUserDataStream(in_memory=True, on_event=lambda e: received.append(e))
        stream.connect()
        event = StreamEvent(
            kind=StreamEventKind.EXECUTION_REPORT,
            timestamp_ns=300,
            symbol="ETHUSDT",
        )
        stream.inject_mock_event(event)
        assert len(received) == 1

    def test_parse_execution_report(self):
        from execution_engine.adapters.binance_ws import (
            BinanceUserDataStream,
            StreamEventKind,
        )

        stream = BinanceUserDataStream(in_memory=True)
        msg = {
            "e": "executionReport",
            "s": "BTCUSDT",
            "i": 99,
            "S": "SELL",
            "X": "FILLED",
            "l": "0.1",
            "L": "43000.5",
        }
        result = stream._parse_message(msg)
        assert result is not None
        assert result.kind == StreamEventKind.EXECUTION_REPORT
        assert result.symbol == "BTCUSDT"
        assert result.side == "SELL"

    def test_parse_balance_update(self):
        from execution_engine.adapters.binance_ws import BinanceUserDataStream

        stream = BinanceUserDataStream(in_memory=True)
        msg = {
            "e": "outboundAccountPosition",
            "B": [{"a": "ETH", "f": "10.5", "l": "2.0"}],
        }
        result = stream._parse_message(msg)
        assert result is not None
        assert result.asset == "ETH"
        assert result.free == 10.5


# ---------------------------------------------------------------------------
# I-33 — LOB Performance Benchmark
# ---------------------------------------------------------------------------


class TestLobBenchmark:
    """I-33: C++ LOB benchmark reference."""

    def test_python_benchmark_runs(self):
        from tests.bench.test_lob_performance_bench import (
            bench_python_sortedcontainers_lob,
        )

        result = bench_python_sortedcontainers_lob(n_ops=100)
        assert result.ops_per_second > 0
        assert result.total_ops == 100

    def test_decision_doc_exists(self):
        doc = Path("docs/lob_implementation_decision.md")
        assert doc.exists()
        content = doc.read_text()
        assert "Kautenja" in content
        assert "sortedcontainers" in content


# ---------------------------------------------------------------------------
# I-37 — n8n Pipeline Client
# ---------------------------------------------------------------------------


class TestN8nPipeline:
    """I-37: n8n REST client for web_autolearn."""

    def test_import(self):
        from sensory.web_autolearn.n8n_pipeline import (  # noqa: F401
            N8nExecutionResult,
            N8nPipelineClient,
            N8nWorkflow,
            WebhookPayload,
        )

    def test_list_workflows_empty(self):
        from sensory.web_autolearn.n8n_pipeline import N8nPipelineClient

        client = N8nPipelineClient(in_memory=True)
        assert client.list_workflows() == []

    def test_register_and_list_workflows(self):
        from sensory.web_autolearn.n8n_pipeline import N8nPipelineClient, N8nWorkflow

        client = N8nPipelineClient(in_memory=True)
        wf = N8nWorkflow(workflow_id="wf-1", name="News Crawler", active=True)
        client.register_mock_workflow(wf)
        workflows = client.list_workflows()
        assert len(workflows) == 1
        assert workflows[0].name == "News Crawler"

    def test_trigger_workflow(self):
        from sensory.web_autolearn.n8n_pipeline import N8nPipelineClient

        client = N8nPipelineClient(in_memory=True)
        result = client.trigger_workflow("wf-1", input_data={"source": "reuters"})
        assert result.status == "success"
        assert result.workflow_id == "wf-1"
        assert result.timestamp_ns > 0

    def test_execution_log(self):
        from sensory.web_autolearn.n8n_pipeline import N8nPipelineClient

        client = N8nPipelineClient(in_memory=True)
        client.trigger_workflow("wf-1")
        client.trigger_workflow("wf-2")
        assert len(client.execution_log) == 2

    def test_process_webhook(self):
        from sensory.web_autolearn.n8n_pipeline import (
            N8nPipelineClient,
            WebhookPayload,
        )

        client = N8nPipelineClient(in_memory=True)
        payload = WebhookPayload(
            workflow_id="wf-1",
            documents=[{"url": "http://example.com", "title": "News"}],
        )
        count = client.process_webhook(payload)
        assert count == 1

    def test_docs_exist(self):
        doc = Path("docs/n8n_workflow_setup.md")
        assert doc.exists()
        content = doc.read_text()
        assert "n8n" in content


# ---------------------------------------------------------------------------
# I-39 — Nomad Job Spec
# ---------------------------------------------------------------------------


class TestNomadSpec:
    """I-39: Nomad container orchestration spec."""

    def test_nomad_file_exists(self):
        nomad = Path("infrastructure/nomad/dixvision.nomad")
        assert nomad.exists()

    def test_nomad_contains_services(self):
        content = Path("infrastructure/nomad/dixvision.nomad").read_text()
        assert "dix-runtime" in content
        assert "dix-learning" in content
        assert "dix-governance" in content
        assert "dix-ui" in content

    def test_nomad_has_health_checks(self):
        content = Path("infrastructure/nomad/dixvision.nomad").read_text()
        assert "/health" in content
        assert 'type     = "http"' in content

    def test_nomad_has_rolling_deploy(self):
        content = Path("infrastructure/nomad/dixvision.nomad").read_text()
        assert "auto_revert" in content
        assert "max_parallel" in content

    def test_readme_exists(self):
        readme = Path("infrastructure/nomad/README.md")
        assert readme.exists()
        content = readme.read_text()
        assert "Nomad" in content
        assert "Kubernetes" in content

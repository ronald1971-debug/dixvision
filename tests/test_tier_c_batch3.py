"""Tests for Tier C batch 3: C-72..C-85 (security, sandboxes, market data, voice)."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# C-73: gVisor sandbox
# ---------------------------------------------------------------------------


def test_gvisor_mock_run() -> None:
    from evolution_engine.patch_pipeline.gvisor_sandbox import GVisorSandbox

    sandbox = GVisorSandbox(in_memory=True)
    result = sandbox.run(["python", "-c", "print('hello')"])
    assert result.exit_code == 0
    assert "python" in result.stdout
    assert len(sandbox.executions) == 1


# ---------------------------------------------------------------------------
# C-74: Firecracker sandbox
# ---------------------------------------------------------------------------


def test_firecracker_mock_run() -> None:
    from evolution_engine.patch_pipeline.firecracker_sandbox import (
        FirecrackerSandbox,
        MicroVMConfig,
    )

    sandbox = FirecrackerSandbox(in_memory=True)
    config = MicroVMConfig(vcpu_count=2, mem_size_mib=512)
    result = sandbox.run(config, command="python validate.py")
    assert result.exit_code == 0
    assert result.vm_id == "fc-0001"
    assert result.boot_time_ms > 0


# ---------------------------------------------------------------------------
# C-75: TOTP escalation codes
# ---------------------------------------------------------------------------


def test_totp_generate_and_verify() -> None:
    from system_engine.credentials.totp import TOTPManager

    mgr = TOTPManager()
    config = mgr.generate_secret()
    assert len(config.secret) > 0

    code = mgr.now(config.secret)
    assert len(code) == 6
    assert code.isdigit()
    assert mgr.verify(config.secret, code) is True


def test_totp_provisioning_uri() -> None:
    from system_engine.credentials.totp import TOTPConfig, TOTPManager

    mgr = TOTPManager()
    config = TOTPConfig(secret="JBSWY3DPEHPK3PXP", issuer="DIX", account="ops")
    uri = mgr.provisioning_uri(config)
    assert "otpauth://totp/" in uri
    assert "JBSWY3DPEHPK3PXP" in uri


# ---------------------------------------------------------------------------
# C-76: Whisper voice transcriber
# ---------------------------------------------------------------------------


def test_voice_transcriber_mock() -> None:
    from sensory.voice.transcriber import VoiceTranscriber

    t = VoiceTranscriber(in_memory=True)
    result = t.transcribe(b"\x00" * 16000)
    assert result.text == "[mock transcription]"
    assert result.duration_seconds == 1.0


def test_voice_intent_classification() -> None:
    from sensory.voice.transcriber import VoiceTranscriber

    t = VoiceTranscriber()
    assert t.classify_intent("kill all positions now").action == "kill_switch"
    assert t.classify_intent("kill all positions now").requires_confirmation is True
    assert t.classify_intent("what is the status?").action == "status"
    assert t.classify_intent("buy 100 shares of AAPL").action == "trade"
    assert t.classify_intent("escalate autonomy").action == "escalate"
    assert t.classify_intent("hello world").action == "unknown"


# ---------------------------------------------------------------------------
# C-79: Polygon adapter
# ---------------------------------------------------------------------------


def test_polygon_adapter_mock_bars() -> None:
    from execution_engine.adapters.polygon import OHLCVBar, PolygonAdapter

    adapter = PolygonAdapter(in_memory=True)
    adapter.add_mock_bar(
        OHLCVBar(
            symbol="AAPL",
            timestamp_ms=1000,
            open=150.0,
            high=155.0,
            low=149.0,
            close=154.0,
            volume=1_000_000,
        )
    )
    bars = adapter.get_aggs("AAPL")
    assert len(bars) == 1
    assert bars[0].close == 154.0


# ---------------------------------------------------------------------------
# C-80: IEX adapter
# ---------------------------------------------------------------------------


def test_iex_adapter_mock_quote() -> None:
    from execution_engine.adapters.iex import IEXAdapter, IEXQuote

    adapter = IEXAdapter(in_memory=True)
    adapter.add_mock_quote(IEXQuote(symbol="GOOG", latest_price=2800.0))
    quote = adapter.get_quote("GOOG")
    assert quote is not None
    assert quote.latest_price == 2800.0


# ---------------------------------------------------------------------------
# C-81: Alpha Vantage adapter
# ---------------------------------------------------------------------------


def test_alphavantage_mock_rate() -> None:
    from execution_engine.adapters.alphavantage import AlphaVantageAdapter, ForexRate

    adapter = AlphaVantageAdapter(in_memory=True)
    adapter.add_mock_rate(ForexRate(from_currency="EUR", to_currency="USD", rate=1.085))
    rate = adapter.get_exchange_rate("EUR", "USD")
    assert rate is not None
    assert rate.rate == 1.085


# ---------------------------------------------------------------------------
# C-82: Glassnode client
# ---------------------------------------------------------------------------


def test_glassnode_mock_metric() -> None:
    from sensory.onchain.glassnode import GlassnodeClient, GlassnodeMetric

    client = GlassnodeClient(in_memory=True)
    client.add_mock_metric(
        GlassnodeMetric(
            metric="indicators/nvt",
            asset="BTC",
            timestamp=1700000000,
            value=65.3,
        )
    )
    results = client.get_metric("indicators/nvt", asset="BTC")
    assert len(results) == 1
    assert results[0].value == 65.3


# ---------------------------------------------------------------------------
# C-83: Arkham client
# ---------------------------------------------------------------------------


def test_arkham_mock_entity() -> None:
    from sensory.onchain.arkham import ArkhamClient, WalletEntity

    client = ArkhamClient(in_memory=True)
    client.add_mock_entity(
        WalletEntity(
            address="0xabc123",
            entity_type="exchange",
            entity_label="Binance Hot Wallet",
            tags=("binance", "hot-wallet"),
        )
    )
    entity = client.get_entity("0xABC123")
    assert entity is not None
    assert entity.entity_type == "exchange"
    assert "binance" in entity.tags


# ---------------------------------------------------------------------------
# C-85: Nansen client
# ---------------------------------------------------------------------------


def test_nansen_mock_txns() -> None:
    from sensory.onchain.nansen import NansenClient, SmartMoneyTx

    client = NansenClient(in_memory=True)
    client.add_mock_tx(
        SmartMoneyTx(
            address="0x111",
            token="ETH",
            action="buy",
            amount_usd=500_000,
            label="Smart Money",
        )
    )
    client.add_mock_tx(
        SmartMoneyTx(
            address="0x222",
            token="BTC",
            action="sell",
            amount_usd=1_000_000,
            label="Fund",
        )
    )
    txns = client.get_smart_money_txns(token="ETH")
    assert len(txns) == 1
    assert txns[0].amount_usd == 500_000

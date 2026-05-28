"""Tests for missing Tier C items: C-58, C-77, C-78."""

from __future__ import annotations

import dataclasses

import pytest

# ---------------------------------------------------------------------------
# C-58 — TimescaleDB store
# ---------------------------------------------------------------------------


class TestTimescaleStore:
    """C-58: TimescaleDB hypertable time-series storage."""

    def test_import(self):
        from state.timeseries.timescale_store import TimescaleStore, TimeseriesRow  # noqa: F401

    def test_write_row_in_memory(self):
        from state.timeseries.timescale_store import TimescaleStore

        store = TimescaleStore(in_memory=True)
        store.write_row("ohlcv", tags={"symbol": "BTC"}, fields={"close": 42000.0})
        assert store.row_count() == 1
        assert store.row_count("ohlcv") == 1
        assert store.row_count("other") == 0

    def test_write_row_preserves_timestamp(self):
        from state.timeseries.timescale_store import TimescaleStore

        store = TimescaleStore(in_memory=True)
        store.write_row("ticks", timestamp_ns=123456789)
        results = store.query("ticks")
        assert results[0]["timestamp_ns"] == 123456789

    def test_query_filters_by_table(self):
        from state.timeseries.timescale_store import TimescaleStore

        store = TimescaleStore(in_memory=True)
        store.write_row("ohlcv", fields={"close": 100.0})
        store.write_row("trades", fields={"qty": 5.0})
        assert len(store.query("ohlcv")) == 1
        assert len(store.query("trades")) == 1

    def test_query_limit(self):
        from state.timeseries.timescale_store import TimescaleStore

        store = TimescaleStore(in_memory=True)
        for i in range(10):
            store.write_row("ticks", fields={"price": float(i)})
        assert len(store.query("ticks", limit=3)) == 3

    def test_create_hypertable_noop_in_memory(self):
        from state.timeseries.timescale_store import TimescaleStore

        store = TimescaleStore(in_memory=True)
        store.create_hypertable("metrics", time_column="ts")
        # No-op in memory — just ensure no crash

    def test_create_continuous_aggregate_noop_in_memory(self):
        from state.timeseries.timescale_store import TimescaleStore

        store = TimescaleStore(in_memory=True)
        store.create_continuous_aggregate("metrics_5m", "metrics", bucket_seconds=300)
        # No-op in memory

    def test_frozen_row(self):
        from state.timeseries.timescale_store import TimeseriesRow

        row = TimeseriesRow(table="t", timestamp_ns=1)
        with pytest.raises((TypeError, AttributeError, dataclasses.FrozenInstanceError)):
            row.table = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# C-77 — TTS Synthesizer + Voice Alerts
# ---------------------------------------------------------------------------


class TestVoiceSynthesizer:
    """C-77: Coqui TTS voice synthesizer."""

    def test_import(self):
        from sensory.voice.synthesizer import (  # noqa: F401
            SynthesisRequest,
            SynthesisResult,
            VoiceSynthesizer,
        )

    def test_mock_synthesis(self):
        from sensory.voice.synthesizer import SynthesisRequest, VoiceSynthesizer

        synth = VoiceSynthesizer(in_memory=True)
        req = SynthesisRequest(text="CRITICAL: Kill switch activated.")
        result = synth.synthesize(req)
        assert result.output_path.endswith(".wav")
        assert result.duration_seconds > 0
        assert result.model_used == "tts_models/en/ljspeech/vits"

    def test_synthesis_log(self):
        from sensory.voice.synthesizer import SynthesisRequest, VoiceSynthesizer

        synth = VoiceSynthesizer(in_memory=True)
        synth.synthesize(SynthesisRequest(text="Alert one"))
        synth.synthesize(SynthesisRequest(text="Alert two"))
        assert len(synth.synthesis_log) == 2

    def test_alert_templates_exist(self):
        from sensory.voice.synthesizer import ALERT_TEMPLATES

        assert len(ALERT_TEMPLATES) >= 3
        severities = {t.severity for t in ALERT_TEMPLATES}
        assert "CRITICAL" in severities
        assert "HIGH" in severities


class TestVoiceAlertDispatcher:
    """C-77: Voice alert dispatcher."""

    def test_import(self):
        from cockpit.voice_alerts import VoiceAlertDispatcher, VoiceAlertEvent  # noqa: F401

    def test_critical_triggers_alert(self):
        from cockpit.voice_alerts import VoiceAlertDispatcher, VoiceAlertEvent

        dispatcher = VoiceAlertDispatcher(min_severity="CRITICAL")
        event = VoiceAlertEvent(
            severity="CRITICAL",
            message="Kill switch activated",
            governance_mode="HALT",
        )
        result = dispatcher.dispatch(event)
        assert result is not None
        assert result.output_path.endswith(".wav")

    def test_low_severity_no_alert(self):
        from cockpit.voice_alerts import VoiceAlertDispatcher, VoiceAlertEvent

        dispatcher = VoiceAlertDispatcher(min_severity="CRITICAL")
        event = VoiceAlertEvent(severity="LOW", message="Minor issue")
        result = dispatcher.dispatch(event)
        assert result is None

    def test_medium_severity_no_alert(self):
        from cockpit.voice_alerts import VoiceAlertDispatcher, VoiceAlertEvent

        dispatcher = VoiceAlertDispatcher(min_severity="CRITICAL")
        event = VoiceAlertEvent(severity="MEDIUM", message="Warning")
        result = dispatcher.dispatch(event)
        assert result is None

    def test_dispatched_alerts_tracked(self):
        from cockpit.voice_alerts import VoiceAlertDispatcher, VoiceAlertEvent

        dispatcher = VoiceAlertDispatcher(min_severity="HIGH")
        dispatcher.dispatch(VoiceAlertEvent(severity="CRITICAL", message="A"))
        dispatcher.dispatch(VoiceAlertEvent(severity="HIGH", message="B"))
        dispatcher.dispatch(VoiceAlertEvent(severity="LOW", message="C"))
        assert len(dispatcher.dispatched_alerts) == 2


# ---------------------------------------------------------------------------
# C-78 — Flutter mobile cockpit (PATTERN_ONLY — just verify files exist)
# ---------------------------------------------------------------------------


class TestFlutterMobile:
    """C-78: Flutter mobile cockpit architecture docs."""

    def test_readme_exists(self):
        from pathlib import Path

        readme = Path("cockpit/mobile/README.md")
        assert readme.exists(), "cockpit/mobile/README.md missing"

    def test_api_client_dart_exists(self):
        from pathlib import Path

        dart = Path("cockpit/mobile/lib/api_client.dart")
        assert dart.exists(), "cockpit/mobile/lib/api_client.dart missing"

    def test_readme_contains_endpoints(self):
        from pathlib import Path

        content = Path("cockpit/mobile/README.md").read_text()
        assert "/api/operator/summary" in content
        assert "/api/operator/kill" in content
        assert "Kill Switch" in content

"""tests/test_replay.py
DIX VISION v42.2 — Ledger Replay Tests

Tests that ledger reconstruction is deterministic (INV-15): same
input events always produce the same checksum, regardless of how
many times the replay is run.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from state.ledger.reconstructor import LedgerReconstructor, ReconstructionResult


class TestReplayDeterminism:
    """INV-15: replay must be deterministic."""

    def test_empty_stream_produces_empty_checksum(self):
        reconstructor = LedgerReconstructor()
        with patch("state.ledger.reconstructor.get_event_store") as mock_store:
            mock_store.return_value.query.return_value = []
            result = reconstructor.reconstruct(
                stream_kind="SYSTEM",
                since_ts_ns=0,
                ts_ns=1_000_000,
            )
        assert result.event_count == 0
        assert result.checksum == ""
        assert result.state == {}

    def test_same_events_same_checksum(self):
        """Two runs over the same events must produce identical checksums."""
        from state.ledger.event_store import LedgerEvent

        fake_event = LedgerEvent(
            event_id="abc123",
            event_type="SYSTEM",
            sub_type="BOOT_START",
            source="test",
            payload={"msg": "boot"},
            timestamp_utc="2000-01-01T00:00:01Z",
            sequence=0,
            prev_hash="",
            event_hash="deadbeef01234567",
        )

        reconstructor = LedgerReconstructor()
        with patch("state.ledger.reconstructor.get_event_store") as mock_store:
            mock_store.return_value.query.return_value = [fake_event]
            r1 = reconstructor.reconstruct("SYSTEM", ts_ns=1_000_000)
            r2 = reconstructor.reconstruct("SYSTEM", ts_ns=1_000_000)

        assert r1.checksum == r2.checksum
        assert r1.event_count == 1

    def test_reducer_applied_correctly(self):
        """Registered reducers modify state deterministically."""
        from state.ledger.event_store import LedgerEvent

        fake_event = LedgerEvent(
            event_id="ev001",
            event_type="GOVERNANCE",
            sub_type="OPGOV_DECISION",
            source="operator_governance",
            payload={"decision": "approved"},
            timestamp_utc="2000-01-01T00:00:02Z",
            sequence=0,
            prev_hash="",
            event_hash="cafe0001",
        )

        reconstructor = LedgerReconstructor()

        def my_reducer(state: dict, evt) -> dict:
            state["last_decision"] = evt.payload.get("decision", "")
            return state

        reconstructor.register_reducer("GOVERNANCE", my_reducer)

        with patch("state.ledger.reconstructor.get_event_store") as mock_store:
            mock_store.return_value.query.return_value = [fake_event]
            result = reconstructor.reconstruct("GOVERNANCE", ts_ns=2_000_000)

        assert result.state.get("last_decision") == "approved"

    def test_verify_determinism_returns_true_for_consistent_data(self):
        from state.ledger.event_store import LedgerEvent

        fake = LedgerEvent(
            event_id="xyz",
            event_type="MARKET",
            sub_type="TICK",
            source="binance",
            payload={"price": "50000"},
            timestamp_utc="2000-01-01T00:00:03Z",
            sequence=1,
            prev_hash="abc",
            event_hash="11223344",
        )
        reconstructor = LedgerReconstructor()
        with patch("state.ledger.reconstructor.get_event_store") as mock_store:
            mock_store.return_value.query.return_value = [fake]
            ok = reconstructor.verify_determinism("MARKET", ts_ns=1_000_000)
        assert ok is True


class TestReconstructionResult:
    def test_result_is_frozen(self):
        from state.ledger.reconstructor import ReconstructionResult
        result = ReconstructionResult(
            stream_kind="SYSTEM",
            since_ts_ns=0,
            until_ts_ns=1000,
            event_count=1,
            checksum="abc",
            state={"key": "val"},
            ts_ns=100,
        )
        with pytest.raises((AttributeError, TypeError)):
            result.event_count = 99  # type: ignore

"""Tests for Tier 3 persistence layer."""

import tempfile
from pathlib import Path

from state.databases.connection import (
    DatabaseBackend,
    DatabaseConfig,
    DatabaseConnection,
)
from state.databases.migrations import MigrationRunner
from state.databases.schema import (
    TableName,
    generate_all_sql,
    generate_create_sql,
)


def test_schema_generation_sqlite():
    sql = generate_create_sql(TableName.TRADE_LEDGER, dialect="sqlite")
    assert "CREATE TABLE IF NOT EXISTS trade_ledger" in sql
    assert "id TEXT" in sql
    assert "ts_ns INTEGER NOT NULL" in sql
    assert "PRIMARY KEY (id)" in sql


def test_schema_generation_all():
    sql = generate_all_sql(dialect="sqlite")
    for table in TableName:
        assert table.value in sql


def test_connection_sqlite():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test.db")
        config = DatabaseConfig(backend=DatabaseBackend.SQLITE, path=db_path)
        conn = DatabaseConnection(config)
        conn.connect()
        assert conn.is_connected
        conn.initialize_schema()
        assert conn.is_initialized
        conn.close()


def test_insert_and_query():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test.db")
        config = DatabaseConfig(backend=DatabaseBackend.SQLITE, path=db_path)
        conn = DatabaseConnection(config)
        conn.connect()
        conn.initialize_schema()

        # Insert a trader profile
        conn.insert(
            TableName.TRADER_PROFILES,
            data={
                "id": "tp_1",
                "canonical_id": "soros",
                "display_name": "George Soros",
                "archetype": "macro",
                "status": "ACTIVE",
                "credibility_score": 0.95,
                "total_observations": 100,
                "created_ts_ns": 1000,
                "updated_ts_ns": 2000,
            },
        )

        # Query it back
        results = conn.query(
            TableName.TRADER_PROFILES,
            where="canonical_id = ?",
            params=("soros",),
        )
        assert len(results) == 1
        assert results[0]["display_name"] == "George Soros"
        assert results[0]["credibility_score"] == 0.95

        # Count
        count = conn.count(TableName.TRADER_PROFILES)
        assert count == 1

        conn.close()


def test_batch_insert():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test.db")
        config = DatabaseConfig(backend=DatabaseBackend.SQLITE, path=db_path)
        conn = DatabaseConnection(config)
        conn.connect()
        conn.initialize_schema()

        rows = [
            {
                "id": f"sig_{i}",
                "ts_ns": i * 1000,
                "source": "x_sentiment",
                "signal_type": "sentiment",
                "symbol": "BTC",
                "value": 0.5 + i * 0.01,
                "confidence": 0.8,
            }
            for i in range(10)
        ]
        conn.insert_many(TableName.SIGNAL_LOG, rows=rows)

        count = conn.count(TableName.SIGNAL_LOG)
        assert count == 10

        # Query with order
        results = conn.query(
            TableName.SIGNAL_LOG,
            order_by="ts_ns DESC",
            limit=3,
        )
        assert len(results) == 3
        assert results[0]["ts_ns"] == 9000

        conn.close()


def test_migrations():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test.db")
        config = DatabaseConfig(backend=DatabaseBackend.SQLITE, path=db_path)
        conn = DatabaseConnection(config)
        conn.connect()
        conn.initialize_schema()

        runner = MigrationRunner(conn)
        assert runner.current_version() == 0

        applied = runner.run_all()
        assert len(applied) >= 1
        assert runner.current_version() >= 1

        # Running again should be no-op
        applied2 = runner.run_all()
        assert len(applied2) == 0

        conn.close()

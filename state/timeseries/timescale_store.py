# ADAPTED FROM: timescale/timescaledb (PostgreSQL extension)
# (SQL hypertable creation, continuous aggregates, chunk_time_interval;
#  psycopg2 driver: cursor.execute(), connection pooling patterns)
"""C-58 — TimescaleDB time-series storage over PostgreSQL.

This module adapts TimescaleDB's hypertable model for storing
high-frequency trading metrics (OHLCV, execution events, hazard events)
with automatic time-based partitioning.

What survives from upstream (TimescaleDB + psycopg2):
    * **Hypertable creation** — ``SELECT create_hypertable(...)`` with
      ``chunk_time_interval => INTERVAL '1 day'``.
    * **Write pattern** — ``INSERT INTO ... VALUES (...)`` with
      nanosecond-precision timestamps.
    * **Continuous aggregates** — ``CREATE MATERIALIZED VIEW ... WITH
      (timescaledb.continuous)`` for live dashboards.
    * **Query pattern** — ``time_bucket()`` for downsampled queries.

What we replaced:
    * Real ``psycopg2`` import is lazy (Protocol seam).
    * In-memory buffer for unit tests (no PostgreSQL instance needed).
    * Same interface pattern as ``influxdb_store.py``.

OFFLINE tier for analytics queries.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from system.time_source import wall_ns


@dataclass(frozen=True, slots=True)
class TimeseriesRow:
    """A single time-series row for TimescaleDB."""

    table: str
    timestamp_ns: int = 0
    tags: Mapping[str, str] = field(default_factory=dict)
    fields: Mapping[str, float | int | str] = field(default_factory=dict)


class TimescaleStore:
    """TimescaleDB write/query client for trading metrics.

    Mirrors TimescaleDB hypertable INSERT/SELECT patterns via psycopg2.

    In test mode (default), buffers rows in-memory.
    """

    def __init__(
        self,
        *,
        dsn: str = "postgresql://localhost:5432/dix_metrics",
        chunk_interval: str = "1 day",
        in_memory: bool = True,
    ) -> None:
        self._dsn = dsn
        self._chunk_interval = chunk_interval
        self._in_memory = in_memory
        self._buffer: list[TimeseriesRow] = []

    def write_row(
        self,
        table: str,
        *,
        tags: Mapping[str, str] | None = None,
        fields: Mapping[str, float | int | str] | None = None,
        timestamp_ns: int | None = None,
    ) -> None:
        """Write a single time-series row.

        Mirrors ``INSERT INTO <hypertable> (time, ...) VALUES (...)``.
        """
        ts = timestamp_ns if timestamp_ns is not None else wall_ns()
        row = TimeseriesRow(
            table=table,
            tags=tags or {},
            fields=fields or {},
            timestamp_ns=ts,
        )
        if self._in_memory:
            self._buffer.append(row)
        else:
            self._write_remote(row)

    def query(
        self,
        table: str,
        *,
        bucket_seconds: int = 60,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Query time-bucketed data from a hypertable.

        In-memory mode: returns buffered rows.
        Production: uses ``time_bucket()`` aggregate.
        """
        if self._in_memory:
            return self._query_buffer(table, limit=limit)
        return self._query_remote(table, bucket_seconds=bucket_seconds, limit=limit)

    def row_count(self, table: str | None = None) -> int:
        """Return number of buffered rows."""
        if table is None:
            return len(self._buffer)
        return sum(1 for r in self._buffer if r.table == table)

    def create_hypertable(self, table: str, time_column: str = "time") -> None:
        """Create a hypertable with automatic time partitioning.

        In-memory mode: no-op.
        Production: ``SELECT create_hypertable('<table>', '<time_column>',
        chunk_time_interval => INTERVAL '<chunk_interval>')``.
        """
        if self._in_memory:
            return
        self._exec_sql(
            f"SELECT create_hypertable('{table}', '{time_column}', "
            f"chunk_time_interval => INTERVAL '{self._chunk_interval}')"
        )

    def create_continuous_aggregate(
        self,
        view_name: str,
        table: str,
        *,
        bucket_seconds: int = 300,
        agg_columns: list[str] | None = None,
    ) -> None:
        """Create a continuous aggregate materialized view.

        In-memory mode: no-op.
        Production: ``CREATE MATERIALIZED VIEW ... WITH
        (timescaledb.continuous)``.
        """
        if self._in_memory:
            return
        cols = ", ".join(agg_columns) if agg_columns else "*"
        sql = (
            f"CREATE MATERIALIZED VIEW {view_name} "
            f"WITH (timescaledb.continuous) AS "
            f"SELECT time_bucket('{bucket_seconds} seconds', time) AS bucket, {cols} "
            f"FROM {table} GROUP BY bucket"
        )
        self._exec_sql(sql)

    # ---- internals -------------------------------------------------------

    def _write_remote(self, row: TimeseriesRow) -> None:
        """Write to TimescaleDB via psycopg2."""
        try:
            import psycopg2  # noqa: F401  # lazy import

            conn = psycopg2.connect(self._dsn)
            cur = conn.cursor()
            columns = ["time"] + list(row.tags.keys()) + list(row.fields.keys())
            values = [row.timestamp_ns] + list(row.tags.values()) + list(row.fields.values())
            placeholders = ", ".join(["%s"] * len(values))
            col_str = ", ".join(columns)
            cur.execute(
                f"INSERT INTO {row.table} ({col_str}) VALUES ({placeholders})",
                values,
            )
            conn.commit()
            cur.close()
            conn.close()
        except ImportError:
            self._buffer.append(row)

    def _query_remote(self, table: str, *, bucket_seconds: int, limit: int) -> list[dict[str, Any]]:
        """Query TimescaleDB with time_bucket aggregation."""
        try:
            import psycopg2  # noqa: F401  # lazy import

            conn = psycopg2.connect(self._dsn)
            cur = conn.cursor()
            cur.execute(
                f"SELECT time_bucket('{bucket_seconds} seconds', time) AS bucket, * "
                f"FROM {table} ORDER BY bucket DESC LIMIT {limit}"
            )
            columns = [desc[0] for desc in cur.description]
            results: list[dict[str, Any]] = []
            for row_data in cur.fetchall():
                results.append(dict(zip(columns, row_data, strict=False)))
            cur.close()
            conn.close()
            return results
        except ImportError:
            return []

    def _query_buffer(self, table: str, *, limit: int) -> list[dict[str, Any]]:
        """Simple in-memory query for testing."""
        results: list[dict[str, Any]] = []
        for row in self._buffer:
            if row.table != table:
                continue
            entry: dict[str, Any] = {
                "table": row.table,
                "timestamp_ns": row.timestamp_ns,
            }
            entry.update(row.tags)
            entry.update(row.fields)
            results.append(entry)
            if len(results) >= limit:
                break
        return results

    def _exec_sql(self, sql: str) -> None:
        """Execute arbitrary SQL."""
        try:
            import psycopg2  # noqa: F401  # lazy import

            conn = psycopg2.connect(self._dsn)
            cur = conn.cursor()
            cur.execute(sql)
            conn.commit()
            cur.close()
            conn.close()
        except ImportError:
            pass


__all__ = ["TimescaleStore", "TimeseriesRow"]

# ADAPTED FROM: ClickHouse/clickhouse-connect
# (clickhouse_connect/driver/client.py — Client, query(), command(), insert();
#  clickhouse_connect/driver/query.py — QueryResult, column_names, result_rows;
#  clickhouse_connect/datatypes/ — type mapping for Float64, UInt64, String)
"""C-57 — ClickHouse columnar analytics store.

This module adapts ``clickhouse-connect`` for high-performance OLAP
queries over trade history, PnL analytics, and backtesting results.

What survives from upstream (ClickHouse/clickhouse-connect):
    * **Client** — ``client.py``: ``get_client(host, port)`` connection.
    * **query()** — ``client.py``: ``client.query(sql)`` returning
      ``QueryResult`` with ``.result_rows`` and ``.column_names``.
    * **insert()** — ``client.py``: ``client.insert(table, data, column_names)``
      for bulk columnar inserts.
    * **command()** — ``client.py``: DDL statements (CREATE TABLE, etc.).

What we replaced:
    * Real ``clickhouse_connect`` import is lazy (Protocol seam).
    * In-memory columnar store for unit tests.
    * Same analytics interface as other state stores.

OFFLINE tier: analytics queries are batch, never on hot path.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class QueryResult:
    """Result of a ClickHouse query."""

    column_names: tuple[str, ...]
    result_rows: tuple[tuple[Any, ...], ...]
    row_count: int = 0


class ClickHouseStore:
    """ClickHouse columnar analytics store.

    Mirrors ``clickhouse_connect.get_client()`` + ``client.query()`` /
    ``client.insert()`` patterns. In test mode, uses in-memory columnar
    buffers.

    Usage::

        store = ClickHouseStore()
        store.insert("trades", [("AAPL", 150.0, 100)], columns=["sym", "px", "qty"])
        result = store.query("SELECT sym, sum(qty) FROM trades GROUP BY sym")
    """

    def __init__(
        self,
        *,
        host: str = "localhost",
        port: int = 8123,
        database: str = "dix",
        in_memory: bool = True,
    ) -> None:
        self._host = host
        self._port = port
        self._database = database
        self._in_memory = in_memory
        self._tables: dict[str, _Table] = {}

    def insert(
        self,
        table: str,
        data: Sequence[tuple[Any, ...]],
        *,
        columns: Sequence[str] | None = None,
    ) -> int:
        """Insert rows into a table (columnar bulk insert).

        Mirrors ``client.insert(table, data, column_names=columns)``.
        """
        if self._in_memory:
            if table not in self._tables:
                self._tables[table] = _Table(columns=list(columns or []))
            t = self._tables[table]
            for row in data:
                t.rows.append(row)
            return len(data)
        return self._insert_remote(table, data, columns)

    def query(self, sql: str) -> QueryResult:
        """Execute a SQL query.

        Mirrors ``client.query(sql).result_rows``.
        """
        if self._in_memory:
            return self._query_buffer(sql)
        return self._query_remote(sql)

    def command(self, sql: str) -> None:
        """Execute a DDL command (CREATE TABLE, etc.)."""
        if self._in_memory:
            return
        self._command_remote(sql)

    def table_row_count(self, table: str) -> int:
        """Return number of rows in a table."""
        if self._in_memory:
            t = self._tables.get(table)
            return len(t.rows) if t else 0
        result = self.query(f"SELECT count() FROM {table}")
        if result.result_rows:
            return int(result.result_rows[0][0])
        return 0

    # ---- internals -------------------------------------------------------

    def _query_buffer(self, sql: str) -> QueryResult:
        """Simple in-memory query (returns all rows from first mentioned table)."""
        for table_name, table in self._tables.items():
            if table_name in sql:
                return QueryResult(
                    column_names=tuple(table.columns),
                    result_rows=tuple(table.rows),
                    row_count=len(table.rows),
                )
        return QueryResult(column_names=(), result_rows=(), row_count=0)

    def _insert_remote(
        self,
        table: str,
        data: Sequence[tuple[Any, ...]],
        columns: Sequence[str] | None,
    ) -> int:
        try:
            import clickhouse_connect

            client = clickhouse_connect.get_client(
                host=self._host, port=self._port, database=self._database
            )
            client.insert(table, list(data), column_names=list(columns or []))
            return len(data)
        except ImportError:
            return 0

    def _query_remote(self, sql: str) -> QueryResult:
        try:
            import clickhouse_connect

            client = clickhouse_connect.get_client(
                host=self._host, port=self._port, database=self._database
            )
            result = client.query(sql)
            return QueryResult(
                column_names=tuple(result.column_names),
                result_rows=tuple(result.result_rows),
                row_count=len(result.result_rows),
            )
        except ImportError:
            return QueryResult(column_names=(), result_rows=(), row_count=0)

    def _command_remote(self, sql: str) -> None:
        try:
            import clickhouse_connect

            client = clickhouse_connect.get_client(
                host=self._host, port=self._port, database=self._database
            )
            client.command(sql)
        except ImportError:
            pass


@dataclass
class _Table:
    columns: list[str]
    rows: list[tuple[Any, ...]] | None = None

    def __post_init__(self) -> None:
        if self.rows is None:
            self.rows = []


__all__ = ["ClickHouseStore", "QueryResult"]

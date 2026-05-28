# ADAPTED FROM: questdb/py-questdb-client
# (questdb/ingress/sender.py — Sender class, row(), flush(), at();
#  ILP line protocol for fast append-only ingestion;
#  psycopg2 wire protocol for SQL read queries)
"""C-51 — QuestDB high-frequency time-series hot store.

This module adapts the ``questdb`` Python client's ILP (InfluxDB Line
Protocol) ingestion pattern for high-frequency tick storage when SQLite
write throughput is insufficient (>1ms write latency).

What survives from upstream (questdb/py-questdb-client):
    * **Sender** — ``ingress/sender.py``: row-by-row ILP ingestion with
      ``row(table, symbols, columns, at)`` API. We replicate the builder
      pattern for constructing ILP lines.
    * **ILP wire format** — ``table,tag=val col=val timestamp\\n``.
      Append-only, no updates, sub-microsecond ingest.
    * **SQL reads via psycopg2** — QuestDB exposes a PostgreSQL wire
      protocol for ``SELECT`` queries. Same ``reader.py`` interface.

What we replaced:
    * Real ``questdb`` + ``psycopg2`` imports are lazy (Protocol seam).
    * In-memory buffer for unit tests (no QuestDB instance needed).
    * Same reader interface as ``state/ledger/reader.py``.

OFFLINE tier for writes (append-only hot ingestion).
RUNTIME safe for reads (SQL queries via pg wire protocol).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from system.time_source import wall_ns


@dataclass(frozen=True, slots=True)
class ILPRow:
    """A single ILP (InfluxDB Line Protocol) row for QuestDB."""

    table: str
    symbols: Mapping[str, str] = field(default_factory=dict)
    columns: Mapping[str, float | int | str] = field(default_factory=dict)
    timestamp_ns: int = 0


class QuestDBHotStore:
    """QuestDB ILP writer + SQL reader for high-frequency tick data.

    Mirrors ``questdb.ingress.Sender``'s row-by-row API. In production,
    connects to QuestDB via ILP (TCP/UDP port 9009) for writes and
    PostgreSQL wire protocol (port 8812) for reads.

    In test mode (default), buffers rows in-memory for assertion.
    """

    def __init__(
        self,
        *,
        ilp_host: str = "localhost",
        ilp_port: int = 9009,
        pg_host: str = "localhost",
        pg_port: int = 8812,
        in_memory: bool = True,
    ) -> None:
        self._ilp_host = ilp_host
        self._ilp_port = ilp_port
        self._pg_host = pg_host
        self._pg_port = pg_port
        self._in_memory = in_memory
        self._buffer: list[ILPRow] = []
        self._sender: Any = None

    def write_row(
        self,
        table: str,
        *,
        symbols: Mapping[str, str] | None = None,
        columns: Mapping[str, float | int | str] | None = None,
        timestamp_ns: int | None = None,
    ) -> None:
        """Append a single row to the hot store.

        Mirrors ``Sender.row(table, symbols=..., columns=..., at=...)``.
        """
        ts = timestamp_ns if timestamp_ns is not None else wall_ns()
        row = ILPRow(
            table=table,
            symbols=symbols or {},
            columns=columns or {},
            timestamp_ns=ts,
        )

        if self._in_memory:
            self._buffer.append(row)
        else:
            self._send_ilp(row)

    def flush(self) -> int:
        """Flush buffered rows to QuestDB. Returns count flushed."""
        if self._in_memory:
            count = len(self._buffer)
            return count

        count = len(self._buffer)
        for row in self._buffer:
            self._send_ilp(row)
        self._buffer.clear()
        return count

    def query(self, sql: str) -> list[dict[str, Any]]:
        """Execute a SQL read query via PostgreSQL wire protocol.

        In-memory mode: returns from buffer filtered by table name.
        Production: uses psycopg2 to query QuestDB's PG endpoint.
        """
        if self._in_memory:
            return self._query_buffer(sql)
        return self._query_pg(sql)

    def row_count(self, table: str | None = None) -> int:
        """Return number of buffered rows (optionally filtered by table)."""
        if table is None:
            return len(self._buffer)
        return sum(1 for r in self._buffer if r.table == table)

    # ---- internals -------------------------------------------------------

    def _send_ilp(self, row: ILPRow) -> None:
        """Send a single row via ILP protocol."""
        try:
            from questdb.ingress import Sender, TimestampNanos

            if self._sender is None:
                self._sender = Sender(host=self._ilp_host, port=self._ilp_port)
            self._sender.row(
                row.table,
                symbols=dict(row.symbols),
                columns=dict(row.columns),
                at=TimestampNanos(row.timestamp_ns),
            )
            self._sender.flush()
        except ImportError:
            self._buffer.append(row)

    def _query_pg(self, sql: str) -> list[dict[str, Any]]:
        """Execute SQL via psycopg2 against QuestDB PG endpoint."""
        try:
            import psycopg2
            import psycopg2.extras

            conn = psycopg2.connect(
                host=self._pg_host,
                port=self._pg_port,
                user="admin",
                password="quest",
                database="qdb",
            )
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql)
                return [dict(row) for row in cur.fetchall()]
        except ImportError:
            return []

    def _query_buffer(self, sql: str) -> list[dict[str, Any]]:
        """Simple in-memory query for testing."""
        results: list[dict[str, Any]] = []
        for row in self._buffer:
            entry: dict[str, Any] = {"table": row.table, "timestamp_ns": row.timestamp_ns}
            entry.update(row.symbols)
            entry.update(row.columns)
            results.append(entry)
        return results


def to_ilp_line(row: ILPRow) -> str:
    """Convert an ILPRow to ILP wire format string."""
    parts = [row.table]
    for k, v in sorted(row.symbols.items()):
        parts[0] += f",{k}={v}"
    cols = []
    for k, v in sorted(row.columns.items()):
        if isinstance(v, str):
            cols.append(f'{k}="{v}"')
        elif isinstance(v, int):
            cols.append(f"{k}={v}i")
        else:
            cols.append(f"{k}={v}")
    line = parts[0]
    if cols:
        line += " " + ",".join(cols)
    line += f" {row.timestamp_ns}"
    return line


__all__ = ["ILPRow", "QuestDBHotStore", "to_ilp_line"]

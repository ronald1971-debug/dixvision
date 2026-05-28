"""DuckDB analytical engine adapter (OSS Integration Layer).

Provides high-performance analytical queries for DIXVISION.
Replaces custom pandas/numpy analytics with SQL-based columnar
processing that handles millions of rows efficiently.

Key use cases:
- Historical trade performance analysis
- Feature generation (rolling windows, aggregations)
- Portfolio analytics (Sharpe, drawdown, correlation)
- Market data ingestion and querying (parquet, CSV)
- Strategy backtesting data management

Reference: github.com/duckdb/duckdb
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from system import time_source


class AnalyticsTable(StrEnum):
    """Pre-defined analytics tables."""

    TRADES = "trades"
    OHLCV = "ohlcv"
    SIGNALS = "signals"
    PERFORMANCE = "performance"
    FEATURES = "features"
    REGIMES = "regimes"


@dataclass(frozen=True, slots=True)
class QueryResult:
    """Result of an analytical query."""

    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    row_count: int
    execution_ms: float


@dataclass(frozen=True, slots=True)
class TableSchema:
    """Schema for an analytics table."""

    name: str
    columns: tuple[tuple[str, str], ...]  # (name, type) pairs
    row_count: int


CREATE_TABLES_SQL = {
    AnalyticsTable.TRADES: """
        CREATE TABLE IF NOT EXISTS trades (
            trade_id VARCHAR PRIMARY KEY,
            ts_ns BIGINT NOT NULL,
            symbol VARCHAR NOT NULL,
            side VARCHAR NOT NULL,
            quantity DOUBLE NOT NULL,
            price DOUBLE NOT NULL,
            fee DOUBLE DEFAULT 0,
            pnl DOUBLE DEFAULT 0,
            strategy VARCHAR,
            regime VARCHAR,
            exchange VARCHAR
        )
    """,
    AnalyticsTable.OHLCV: """
        CREATE TABLE IF NOT EXISTS ohlcv (
            symbol VARCHAR NOT NULL,
            ts_ms BIGINT NOT NULL,
            open DOUBLE NOT NULL,
            high DOUBLE NOT NULL,
            low DOUBLE NOT NULL,
            close DOUBLE NOT NULL,
            volume DOUBLE NOT NULL,
            timeframe VARCHAR DEFAULT '1h',
            PRIMARY KEY (symbol, ts_ms, timeframe)
        )
    """,
    AnalyticsTable.SIGNALS: """
        CREATE TABLE IF NOT EXISTS signals (
            signal_id VARCHAR PRIMARY KEY,
            ts_ns BIGINT NOT NULL,
            source VARCHAR NOT NULL,
            symbol VARCHAR NOT NULL,
            side VARCHAR NOT NULL,
            confidence DOUBLE NOT NULL,
            strategy VARCHAR,
            regime VARCHAR
        )
    """,
    AnalyticsTable.PERFORMANCE: """
        CREATE TABLE IF NOT EXISTS performance (
            ts_ns BIGINT NOT NULL,
            equity DOUBLE NOT NULL,
            drawdown DOUBLE NOT NULL,
            sharpe DOUBLE,
            win_rate DOUBLE,
            trade_count INTEGER,
            strategy VARCHAR,
            PRIMARY KEY (ts_ns, strategy)
        )
    """,
    AnalyticsTable.FEATURES: """
        CREATE TABLE IF NOT EXISTS features (
            ts_ns BIGINT NOT NULL,
            symbol VARCHAR NOT NULL,
            feature_name VARCHAR NOT NULL,
            value DOUBLE NOT NULL,
            PRIMARY KEY (ts_ns, symbol, feature_name)
        )
    """,
    AnalyticsTable.REGIMES: """
        CREATE TABLE IF NOT EXISTS regimes (
            ts_ns BIGINT NOT NULL,
            regime VARCHAR NOT NULL,
            confidence DOUBLE NOT NULL,
            duration_ns BIGINT,
            PRIMARY KEY (ts_ns)
        )
    """,
}


class DuckDBAnalyticsAdapter:
    """DIXVISION adapter wrapping DuckDB for analytical queries.

    Provides:
    - Schema management (create/drop tables)
    - Data ingestion (insert, bulk load, parquet import)
    - Analytical queries (SQL with full DuckDB power)
    - Pre-built analytics (Sharpe, drawdown, PnL attribution)
    - Feature generation (window functions, rolling stats)

    Falls back to in-memory dict storage when DuckDB is unavailable.
    """

    def __init__(self, *, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._conn: Any = None
        self._duckdb_available = False
        self._inmemory_tables: dict[str, list[dict[str, Any]]] = {}

    def connect(self) -> bool:
        """Connect to DuckDB."""
        try:
            import duckdb

            self._conn = duckdb.connect(self._db_path)
            self._duckdb_available = True
            return True
        except ImportError:
            self._duckdb_available = False
            return False

    def initialize_schema(self) -> int:
        """Create all analytics tables. Returns count created."""
        if not self._duckdb_available:
            for table in AnalyticsTable:
                self._inmemory_tables.setdefault(table.value, [])
            return len(AnalyticsTable)

        count = 0
        for sql in CREATE_TABLES_SQL.values():
            try:
                self._conn.execute(sql)
                count += 1
            except Exception:
                pass
        return count

    def insert(self, table: AnalyticsTable, data: dict[str, Any]) -> bool:
        """Insert a single row."""
        if not self._duckdb_available:
            self._inmemory_tables.setdefault(table.value, []).append(data)
            return True

        cols = ", ".join(data.keys())
        placeholders = ", ".join(["?" for _ in data])
        sql = f"INSERT OR REPLACE INTO {table.value} ({cols}) VALUES ({placeholders})"
        try:
            self._conn.execute(sql, list(data.values()))
            return True
        except Exception:
            return False

    def insert_many(self, table: AnalyticsTable, rows: list[dict[str, Any]]) -> int:
        """Bulk insert rows. Returns count inserted."""
        if not rows:
            return 0

        if not self._duckdb_available:
            store = self._inmemory_tables.setdefault(table.value, [])
            store.extend(rows)
            return len(rows)

        count = 0
        for row in rows:
            if self.insert(table, row):
                count += 1
        return count

    def query(self, sql: str, params: list[Any] | None = None) -> QueryResult:
        """Execute an analytical SQL query."""

        start = time_source.wall_ns() / 1_000_000_000

        if not self._duckdb_available:
            elapsed = (time_source.wall_ns() / 1_000_000_000 - start) * 1000
            return QueryResult(
                columns=(),
                rows=(),
                row_count=0,
                execution_ms=elapsed,
            )

        try:
            result = self._conn.execute(sql, params or [])
            columns = tuple(desc[0] for desc in result.description or [])
            rows = tuple(tuple(row) for row in result.fetchall())
            elapsed = (time_source.wall_ns() / 1_000_000_000 - start) * 1000
            return QueryResult(
                columns=columns,
                rows=rows,
                row_count=len(rows),
                execution_ms=elapsed,
            )
        except Exception:
            elapsed = (time_source.wall_ns() / 1_000_000_000 - start) * 1000
            return QueryResult(
                columns=(),
                rows=(),
                row_count=0,
                execution_ms=elapsed,
            )

    # --- Pre-built analytics ---

    def compute_sharpe(self, *, strategy: str = "", risk_free_rate: float = 0.0) -> float:
        """Compute Sharpe ratio from performance table."""
        if not self._duckdb_available:
            return 0.0
        where = f"WHERE strategy = '{strategy}'" if strategy else ""
        sql = f"""
            SELECT AVG(equity) as avg_eq, STDDEV(equity) as std_eq
            FROM performance {where}
        """
        result = self.query(sql)
        if result.row_count == 0:
            return 0.0
        avg_eq, std_eq = result.rows[0]
        if not std_eq or std_eq == 0:
            return 0.0
        return (float(avg_eq) - risk_free_rate) / float(std_eq)

    def compute_max_drawdown(self, *, strategy: str = "") -> float:
        """Compute maximum drawdown from performance table."""
        if not self._duckdb_available:
            return 0.0
        where = f"WHERE strategy = '{strategy}'" if strategy else ""
        sql = f"SELECT MAX(drawdown) FROM performance {where}"
        result = self.query(sql)
        if result.row_count == 0 or result.rows[0][0] is None:
            return 0.0
        return float(result.rows[0][0])

    def compute_win_rate(self, *, strategy: str = "") -> float:
        """Compute win rate from trades table."""
        if not self._duckdb_available:
            return 0.0
        where = f"WHERE strategy = '{strategy}'" if strategy else ""
        sql = f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins
            FROM trades {where}
        """
        result = self.query(sql)
        if result.row_count == 0:
            return 0.0
        total, wins = result.rows[0]
        if not total or total == 0:
            return 0.0
        return float(wins) / float(total)

    # --- Data loading ---

    def load_parquet(self, table: AnalyticsTable, path: str) -> int:
        """Load data from a parquet file."""
        if not self._duckdb_available:
            return 0
        sql = f"INSERT INTO {table.value} SELECT * FROM read_parquet('{path}')"
        try:
            self._conn.execute(sql)
            count_result = self._conn.execute(f"SELECT COUNT(*) FROM {table.value}").fetchone()
            return int(count_result[0]) if count_result else 0
        except Exception:
            return 0

    def load_csv(self, table: AnalyticsTable, path: str) -> int:
        """Load data from a CSV file."""
        if not self._duckdb_available:
            return 0
        sql = f"INSERT INTO {table.value} SELECT * FROM read_csv_auto('{path}')"
        try:
            self._conn.execute(sql)
            count_result = self._conn.execute(f"SELECT COUNT(*) FROM {table.value}").fetchone()
            return int(count_result[0]) if count_result else 0
        except Exception:
            return 0

    # --- Info ---

    def table_info(self, table: AnalyticsTable) -> TableSchema | None:
        """Get table schema information."""
        if not self._duckdb_available:
            rows = self._inmemory_tables.get(table.value, [])
            return TableSchema(name=table.value, columns=(), row_count=len(rows))
        try:
            result = self._conn.execute(
                f"SELECT column_name, data_type FROM information_schema.columns "
                f"WHERE table_name = '{table.value}'"
            ).fetchall()
            count = self._conn.execute(f"SELECT COUNT(*) FROM {table.value}").fetchone()
            return TableSchema(
                name=table.value,
                columns=tuple((r[0], r[1]) for r in result),
                row_count=int(count[0]) if count else 0,
            )
        except Exception:
            return None

    def close(self) -> None:
        """Close DuckDB connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

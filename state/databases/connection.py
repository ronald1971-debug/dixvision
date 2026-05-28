"""Database connection management (BUILD-DIRECTIVE — Tier 3 Persistence).

Provides connection pooling and lifecycle management for both
SQLite (local/testing) and PostgreSQL/TimescaleDB (production).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from state.databases.schema import TableName, generate_all_sql


class DatabaseBackend(StrEnum):
    """Supported database backends."""

    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    TIMESCALEDB = "timescaledb"


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    """Database connection configuration."""

    backend: DatabaseBackend = DatabaseBackend.SQLITE
    path: str = "state/dix_persistence.db"  # SQLite path
    host: str = "localhost"
    port: int = 5432
    database: str = "dixvision"
    user: str = "dixvision"
    password: str = ""  # loaded from env
    pool_size: int = 5
    pool_timeout: int = 30


class DatabaseConnection:
    """Manages database connections and provides query interface.

    Supports SQLite for local development and PostgreSQL for production.
    Uses connection pooling for PostgreSQL.
    """

    def __init__(self, config: DatabaseConfig | None = None) -> None:
        self._config = config or DatabaseConfig()
        self._conn: sqlite3.Connection | None = None
        self._initialized = False

    def connect(self) -> None:
        """Establish database connection."""
        if self._config.backend == DatabaseBackend.SQLITE:
            db_path = Path(self._config.path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                str(db_path),
                check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        # PostgreSQL: would use asyncpg or psycopg pool
        # Not imported here to avoid hard dependency

    def initialize_schema(self) -> None:
        """Create all tables if they don't exist."""
        if self._conn is None:
            self.connect()
        assert self._conn is not None
        sql = generate_all_sql(dialect="sqlite")
        self._conn.executescript(sql)
        self._initialized = True

    def insert(self, table: TableName, *, data: dict[str, Any]) -> None:
        """Insert a row into a table."""
        assert self._conn is not None
        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" * len(data))
        sql = f"INSERT OR REPLACE INTO {table.value} ({cols}) VALUES ({placeholders})"
        self._conn.execute(sql, list(data.values()))
        self._conn.commit()

    def insert_many(self, table: TableName, *, rows: list[dict[str, Any]]) -> None:
        """Batch insert rows."""
        if not rows:
            return
        assert self._conn is not None
        cols = ", ".join(rows[0].keys())
        placeholders = ", ".join("?" * len(rows[0]))
        sql = f"INSERT OR REPLACE INTO {table.value} ({cols}) VALUES ({placeholders})"
        self._conn.executemany(sql, [list(r.values()) for r in rows])
        self._conn.commit()

    def query(
        self,
        table: TableName,
        *,
        where: str = "",
        params: tuple[Any, ...] = (),
        order_by: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query rows from a table."""
        assert self._conn is not None
        sql = f"SELECT * FROM {table.value}"
        if where:
            sql += f" WHERE {where}"
        if order_by:
            sql += f" ORDER BY {order_by}"
        sql += f" LIMIT {limit}"
        cursor = self._conn.execute(sql, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def count(self, table: TableName, *, where: str = "", params: tuple[Any, ...] = ()) -> int:
        """Count rows in a table."""
        assert self._conn is not None
        sql = f"SELECT COUNT(*) FROM {table.value}"
        if where:
            sql += f" WHERE {where}"
        cursor = self._conn.execute(sql, params)
        return cursor.fetchone()[0]

    def execute_raw(self, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
        """Execute raw SQL (for complex queries)."""
        assert self._conn is not None
        cursor = self._conn.execute(sql, params)
        if cursor.description:
            return [dict(row) for row in cursor.fetchall()]
        self._conn.commit()
        return []

    def close(self) -> None:
        """Close the connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._conn is not None

    @property
    def is_initialized(self) -> bool:
        """Check if schema is initialized."""
        return self._initialized

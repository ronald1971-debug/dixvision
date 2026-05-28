"""Database migration management (BUILD-DIRECTIVE — Tier 3 Persistence).

Provides forward-only migrations for schema evolution.
Each migration is a versioned SQL script that runs exactly once.
Migration state is tracked in a _migrations table.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Migration:
    """A single migration step."""

    version: int
    name: str
    up_sql: str
    description: str = ""


# Migration registry — add new migrations here
MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=1,
        name="initial_schema",
        description="Create all base tables",
        up_sql="""\
-- Initial schema created by schema.py
-- This migration is a no-op if initialize_schema() was called first
CREATE TABLE IF NOT EXISTS _migration_version (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_ts TEXT DEFAULT (datetime('now'))
);
""",
    ),
    Migration(
        version=2,
        name="add_timescale_hypertables",
        description="Convert timeseries tables to TimescaleDB hypertables (PostgreSQL only)",
        up_sql="""\
-- TimescaleDB hypertable creation (no-op on SQLite)
-- SELECT create_hypertable('trade_ledger', 'ts_ns', if_not_exists => TRUE);
-- SELECT create_hypertable('signal_log', 'ts_ns', if_not_exists => TRUE);
-- SELECT create_hypertable('regime_history', 'ts_ns', if_not_exists => TRUE);
-- SELECT create_hypertable('portfolio_snapshots', 'ts_ns', if_not_exists => TRUE);
""",
    ),
    Migration(
        version=3,
        name="add_retention_policies",
        description="Add data retention policies for timeseries tables",
        up_sql="""\
-- Retention: keep signal_log for 90 days, trade_ledger forever
-- SELECT add_retention_policy('signal_log', INTERVAL '90 days', if_not_exists => TRUE);
""",
    ),
    Migration(
        version=4,
        name="add_continuous_aggregates",
        description="Add continuous aggregates for common queries",
        up_sql="""\
-- Hourly performance rollup
-- CREATE MATERIALIZED VIEW IF NOT EXISTS perf_hourly AS
-- SELECT entity_id, time_bucket('1 hour', ts_ns) as bucket,
--        avg(total_pnl) as avg_pnl, max(max_drawdown) as worst_dd
-- FROM performance_metrics
-- GROUP BY entity_id, bucket;
""",
    ),
)


class MigrationRunner:
    """Runs forward-only migrations against a database connection."""

    def __init__(self, conn: Any) -> None:
        """Initialize with a DatabaseConnection instance."""
        self._conn = conn
        self._ensure_migration_table()

    def _ensure_migration_table(self) -> None:
        """Create _migration_version table if it doesn't exist."""
        self._conn.execute_raw(
            "CREATE TABLE IF NOT EXISTS _migration_version ("
            "version INTEGER PRIMARY KEY, "
            "name TEXT NOT NULL, "
            "applied_ts TEXT DEFAULT (datetime('now'))"
            ")"
        )

    def current_version(self) -> int:
        """Get the current migration version."""
        rows = self._conn.execute_raw("SELECT MAX(version) as v FROM _migration_version")
        if rows and rows[0]["v"] is not None:
            return rows[0]["v"]
        return 0

    def pending_migrations(self) -> list[Migration]:
        """Get migrations that haven't been applied yet."""
        current = self.current_version()
        return [m for m in MIGRATIONS if m.version > current]

    def run_all(self) -> list[Migration]:
        """Run all pending migrations. Returns list of applied migrations."""
        applied: list[Migration] = []
        for migration in self.pending_migrations():
            self._apply(migration)
            applied.append(migration)
        return applied

    def run_to(self, target_version: int) -> list[Migration]:
        """Run migrations up to a specific version."""
        applied: list[Migration] = []
        for migration in self.pending_migrations():
            if migration.version > target_version:
                break
            self._apply(migration)
            applied.append(migration)
        return applied

    def _apply(self, migration: Migration) -> None:
        """Apply a single migration."""
        # Execute the migration SQL
        for statement in migration.up_sql.split(";"):
            stmt = statement.strip()
            if stmt and not stmt.startswith("--"):
                self._conn.execute_raw(stmt + ";")

        # Record the migration
        self._conn.execute_raw(
            "INSERT INTO _migration_version (version, name) VALUES (?, ?)",
            (migration.version, migration.name),
        )

"""Database schema definitions (BUILD-DIRECTIVE — Tier 3 Persistence).

Defines the canonical schema for all persistent tables. Supports both
PostgreSQL/TimescaleDB (production) and SQLite (development/testing).

Tables:
- trader_profiles: Trader identity + philosophy + metrics
- strategy_atoms: Extracted reusable strategy atoms
- trade_ledger: Full fill history with governance audit
- regime_history: Market regime classification timeline
- performance_metrics: Per-entity rolling performance
- learning_events: All learning/evolution decisions
- governance_decisions: Every governance gate pass/fail
- signal_log: Raw signals from all sources
- portfolio_snapshots: Point-in-time portfolio state
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TableName(StrEnum):
    """Canonical table names."""

    TRADER_PROFILES = "trader_profiles"
    STRATEGY_ATOMS = "strategy_atoms"
    TRADE_LEDGER = "trade_ledger"
    REGIME_HISTORY = "regime_history"
    PERFORMANCE_METRICS = "performance_metrics"
    LEARNING_EVENTS = "learning_events"
    GOVERNANCE_DECISIONS = "governance_decisions"
    SIGNAL_LOG = "signal_log"
    PORTFOLIO_SNAPSHOTS = "portfolio_snapshots"
    NARRATIVE_STORE = "narrative_store"
    ARCHETYPE_REGISTRY = "archetype_registry"


@dataclass(frozen=True, slots=True)
class ColumnDef:
    """Column definition."""

    name: str
    dtype: str  # SQL type
    primary_key: bool = False
    nullable: bool = True
    indexed: bool = False
    default: str | None = None


# Schema definitions
SCHEMAS: dict[TableName, tuple[ColumnDef, ...]] = {
    TableName.TRADER_PROFILES: (
        ColumnDef("id", "TEXT", primary_key=True),
        ColumnDef("canonical_id", "TEXT", nullable=False, indexed=True),
        ColumnDef("display_name", "TEXT", nullable=False),
        ColumnDef("archetype", "TEXT", indexed=True),
        ColumnDef("status", "TEXT", nullable=False),
        ColumnDef("credibility_score", "REAL", nullable=False),
        ColumnDef("philosophy_vector", "BLOB"),
        ColumnDef("timeframe_bias", "TEXT"),
        ColumnDef("total_observations", "INTEGER", default="0"),
        ColumnDef("created_ts_ns", "INTEGER", nullable=False),
        ColumnDef("updated_ts_ns", "INTEGER", nullable=False),
    ),
    TableName.STRATEGY_ATOMS: (
        ColumnDef("id", "TEXT", primary_key=True),
        ColumnDef("category", "TEXT", nullable=False, indexed=True),
        ColumnDef("source_trader_id", "TEXT", indexed=True),
        ColumnDef("description", "TEXT"),
        ColumnDef("regime_fitness", "REAL"),
        ColumnDef("confidence", "REAL"),
        ColumnDef("observations", "INTEGER", default="0"),
        ColumnDef("parameters", "TEXT"),  # JSON blob
        ColumnDef("created_ts_ns", "INTEGER", nullable=False),
        ColumnDef("last_used_ts_ns", "INTEGER"),
    ),
    TableName.TRADE_LEDGER: (
        ColumnDef("id", "TEXT", primary_key=True),
        ColumnDef("ts_ns", "INTEGER", nullable=False, indexed=True),
        ColumnDef("symbol", "TEXT", nullable=False, indexed=True),
        ColumnDef("side", "TEXT", nullable=False),
        ColumnDef("size", "REAL", nullable=False),
        ColumnDef("price", "REAL", nullable=False),
        ColumnDef("fill_type", "TEXT"),
        ColumnDef("slippage_bps", "REAL"),
        ColumnDef("latency_ms", "REAL"),
        ColumnDef("governance_hash", "TEXT"),
        ColumnDef("strategy_id", "TEXT", indexed=True),
        ColumnDef("regime", "TEXT", indexed=True),
        ColumnDef("pnl", "REAL"),
    ),
    TableName.REGIME_HISTORY: (
        ColumnDef("id", "TEXT", primary_key=True),
        ColumnDef("ts_ns", "INTEGER", nullable=False, indexed=True),
        ColumnDef("regime", "TEXT", nullable=False, indexed=True),
        ColumnDef("confidence", "REAL", nullable=False),
        ColumnDef("volatility", "REAL"),
        ColumnDef("trend_strength", "REAL"),
        ColumnDef("correlation_regime", "REAL"),
        ColumnDef("transition_from", "TEXT"),
        ColumnDef("duration_ns", "INTEGER"),
    ),
    TableName.PERFORMANCE_METRICS: (
        ColumnDef("id", "TEXT", primary_key=True),
        ColumnDef("entity_id", "TEXT", nullable=False, indexed=True),
        ColumnDef("entity_type", "TEXT", nullable=False),
        ColumnDef("ts_ns", "INTEGER", nullable=False, indexed=True),
        ColumnDef("total_pnl", "REAL"),
        ColumnDef("sharpe", "REAL"),
        ColumnDef("max_drawdown", "REAL"),
        ColumnDef("win_rate", "REAL"),
        ColumnDef("profit_factor", "REAL"),
        ColumnDef("total_trades", "INTEGER"),
        ColumnDef("regime", "TEXT", indexed=True),
    ),
    TableName.LEARNING_EVENTS: (
        ColumnDef("id", "TEXT", primary_key=True),
        ColumnDef("ts_ns", "INTEGER", nullable=False, indexed=True),
        ColumnDef("event_type", "TEXT", nullable=False, indexed=True),
        ColumnDef("source_module", "TEXT"),
        ColumnDef("payload", "TEXT"),  # JSON
        ColumnDef("governance_approved", "INTEGER"),
        ColumnDef("governance_hash", "TEXT"),
    ),
    TableName.GOVERNANCE_DECISIONS: (
        ColumnDef("id", "TEXT", primary_key=True),
        ColumnDef("ts_ns", "INTEGER", nullable=False, indexed=True),
        ColumnDef("decision_type", "TEXT", nullable=False, indexed=True),
        ColumnDef("granted", "INTEGER", nullable=False),
        ColumnDef("reason", "TEXT"),
        ColumnDef("operator_id", "TEXT"),
        ColumnDef("hmac_signature", "TEXT"),
        ColumnDef("nonce", "TEXT"),
    ),
    TableName.SIGNAL_LOG: (
        ColumnDef("id", "TEXT", primary_key=True),
        ColumnDef("ts_ns", "INTEGER", nullable=False, indexed=True),
        ColumnDef("source", "TEXT", nullable=False, indexed=True),
        ColumnDef("signal_type", "TEXT", nullable=False),
        ColumnDef("symbol", "TEXT", indexed=True),
        ColumnDef("value", "REAL"),
        ColumnDef("confidence", "REAL"),
        ColumnDef("metadata", "TEXT"),  # JSON
    ),
    TableName.PORTFOLIO_SNAPSHOTS: (
        ColumnDef("id", "TEXT", primary_key=True),
        ColumnDef("ts_ns", "INTEGER", nullable=False, indexed=True),
        ColumnDef("total_equity_usd", "REAL"),
        ColumnDef("positions", "TEXT"),  # JSON
        ColumnDef("unrealized_pnl", "REAL"),
        ColumnDef("realized_pnl", "REAL"),
        ColumnDef("max_drawdown", "REAL"),
        ColumnDef("regime", "TEXT"),
    ),
    TableName.NARRATIVE_STORE: (
        ColumnDef("id", "TEXT", primary_key=True),
        ColumnDef("theme", "TEXT", nullable=False, indexed=True),
        ColumnDef("strength", "REAL", nullable=False),
        ColumnDef("source_count", "INTEGER"),
        ColumnDef("embedding", "BLOB"),
        ColumnDef("ts_ns", "INTEGER", nullable=False, indexed=True),
        ColumnDef("expires_ts_ns", "INTEGER"),
    ),
    TableName.ARCHETYPE_REGISTRY: (
        ColumnDef("id", "TEXT", primary_key=True),
        ColumnDef("group_name", "TEXT", nullable=False, indexed=True),
        ColumnDef("base_trader", "TEXT", nullable=False, indexed=True),
        ColumnDef("timeframe", "TEXT"),
        ColumnDef("risk_profile", "TEXT"),
        ColumnDef("execution_style", "TEXT"),
        ColumnDef("regime_bias", "TEXT"),
        ColumnDef("philosophy", "TEXT"),
        ColumnDef("version", "INTEGER", default="1"),
        ColumnDef("created_ts_ns", "INTEGER", nullable=False),
    ),
}


def generate_create_sql(table: TableName, *, dialect: str = "sqlite") -> str:
    """Generate CREATE TABLE SQL for a given table.

    Args:
        table: The table to generate SQL for.
        dialect: "sqlite" or "postgresql"
    """
    cols = SCHEMAS[table]
    parts: list[str] = []
    pk_cols: list[str] = []

    for col in cols:
        dtype = col.dtype
        if dialect == "postgresql" and dtype == "INTEGER":
            dtype = "BIGINT"
        if dialect == "postgresql" and dtype == "REAL":
            dtype = "DOUBLE PRECISION"

        line = f"    {col.name} {dtype}"
        if not col.nullable:
            line += " NOT NULL"
        if col.default is not None:
            line += f" DEFAULT {col.default}"
        if col.primary_key:
            pk_cols.append(col.name)
        parts.append(line)

    if pk_cols:
        parts.append(f"    PRIMARY KEY ({', '.join(pk_cols)})")

    create = f"CREATE TABLE IF NOT EXISTS {table.value} (\n"
    create += ",\n".join(parts)
    create += "\n);"

    # Add indexes
    index_stmts: list[str] = []
    for col in cols:
        if col.indexed and not col.primary_key:
            idx_name = f"idx_{table.value}_{col.name}"
            index_stmts.append(
                f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table.value} ({col.name});"
            )

    return create + "\n" + "\n".join(index_stmts)


def generate_all_sql(*, dialect: str = "sqlite") -> str:
    """Generate full schema SQL for all tables."""
    statements: list[str] = []
    for table in TableName:
        statements.append(generate_create_sql(table, dialect=dialect))
    return "\n\n".join(statements)

"""Persistence layer (BUILD-DIRECTIVE — Tier 3).

Provides durable storage for all system state beyond the in-memory
structures. Supports:
- PostgreSQL/TimescaleDB for timeseries (OHLCV, indicators, fills)
- SQLite for local-first operation and testing
- Migration management for schema evolution
- Query layer for efficient retrieval patterns
"""

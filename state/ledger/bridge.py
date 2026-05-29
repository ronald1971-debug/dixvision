"""state.ledger.bridge — unified read-only surface over both ledger chains.

DIX VISION v42.2 maintains two complementary hash-chained ledgers:

1. **Event Store** (``state/ledger/event_store.py`` / ``writer.py``)
   - Stores ALL runtime events: MARKET, SYSTEM, GOVERNANCE, HAZARD
   - Written by: cockpit.chat, security.wallet_policy, system_monitor.*
   - Schema: ``LedgerEvent`` — event_id, event_type, sub_type, source,
     payload, timestamp_utc, sequence, prev_hash, event_hash
   - SQLite WAL, SHA-256 hash-chain, thread-safe via AsyncWriter

2. **Authority Ledger** (``governance_engine/control_plane/ledger_authority_writer.py``)
   - Stores ONLY governance authority decisions: mode transitions,
     strategy lifecycle, operator approvals, HMAC-signed intents
   - Written by: GovernanceEngine (the ONLY permitted writer — GOV-CP-05)
   - Schema: ``LedgerEntry`` — seq, ts_ns, kind, payload, prev_hash, entry_hash
   - SQLite WAL, SHA-256 hash-chain, boot-time integrity check

These are NOT duplicates — they serve different layers of the audit trail:
- Event Store: high-frequency operational events (every tick, every signal)
- Authority Ledger: low-frequency governance decisions (mode changes, approvals)

The ``LedgerBridge`` here provides a unified read-only query surface that
merges both chains for audit-panel use (e.g. the Operator Dashboard
``/api/dashboard/decisions`` endpoint and the authority panel in
``ui/governance_routes.py``).

``state/ledger/reader.py`` already exposes the authority surface via
``authority_entries()``; this module adds the event-store side and a
combined chronological iterator.

Read-only: no writes flow through this module. Writes go to
``state/ledger/writer.get_writer()`` (event store) or
``governance_engine.control_plane.ledger_authority_writer.LedgerAuthorityWriter``
(authority ledger) exclusively.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _ns_to_utc_iso(ts_ns: int) -> str:
    """Convert epoch-nanosecond to ISO-8601 UTC string.

    Pure integer arithmetic — no ``datetime`` or ``time`` import so
    this path stays replay-deterministic (INV-15).
    Uses the proleptic Gregorian civil calendar (Richards, 2013).
    """
    s = ts_ns // 1_000_000_000
    s, sec = divmod(s, 60)
    s, minute = divmod(s, 60)
    day_total, hour = divmod(s, 24)
    # Shift epoch to proleptic Gregorian Mar-1 year-0 reference
    z = day_total + 719468
    era = z // 146097 if z >= 0 else (z - 146096) // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    dy = doy - (153 * mp + 2) // 5 + 1
    mo = mp + (3 if mp < 10 else -9)
    yr = yoe + era * 400 + (1 if mo <= 2 else 0)
    return f"{yr:04d}-{mo:02d}-{dy:02d}T{hour:02d}:{minute:02d}:{sec:02d}Z"


@dataclass(frozen=True, slots=True)
class BridgedEntry:
    """Normalised view of one entry from either ledger chain.

    ``chain`` is ``"event"`` (event store) or ``"authority"``
    (governance authority ledger). ``seq`` is the chain-local sequence
    number.  ``ts_utc`` is an ISO-8601 timestamp string (the two
    chains use different field names; this bridge normalises them).
    ``kind`` is the event/entry kind string. ``payload`` is the raw
    dict.
    """

    chain: str
    seq: int
    ts_utc: str
    kind: str
    source: str
    payload: dict[str, Any]


def _authority_entries(
    db_path: Path | None, limit: int, offset: int
) -> list[BridgedEntry]:
    """Read rows from the authority SQLite file."""
    if db_path is None or not db_path.exists():
        return []
    try:
        import sqlite3

        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT seq, ts_ns, kind, payload FROM ledger_authority "
            "ORDER BY seq LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        conn.close()
        out: list[BridgedEntry] = []
        for r in rows:
            import json as _json

            ts_utc = _ns_to_utc_iso(int(r["ts_ns"]))
            try:
                payload = _json.loads(r["payload"])
            except Exception:
                payload = {"raw": r["payload"]}
            out.append(
                BridgedEntry(
                    chain="authority",
                    seq=int(r["seq"]),
                    ts_utc=ts_utc,
                    kind=str(r["kind"]),
                    source="governance",
                    payload=payload,
                )
            )
        return out
    except Exception:  # pragma: no cover
        return []


def _event_store_entries(
    db_path: Path | None, limit: int, offset: int
) -> list[BridgedEntry]:
    """Read rows from the event-store SQLite file."""
    if db_path is None or not db_path.exists():
        return []
    try:
        import sqlite3

        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT sequence, timestamp_utc, event_type, sub_type, source, payload "
            "FROM events ORDER BY sequence LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        conn.close()
        out: list[BridgedEntry] = []
        for r in rows:
            import json as _json

            try:
                payload = _json.loads(r["payload"])
            except Exception:
                payload = {"raw": r["payload"]}
            out.append(
                BridgedEntry(
                    chain="event",
                    seq=int(r["sequence"]),
                    ts_utc=str(r["timestamp_utc"]),
                    kind=f"{r['event_type']}.{r['sub_type']}",
                    source=str(r["source"]),
                    payload=payload,
                )
            )
        return out
    except Exception:  # pragma: no cover
        return []


class LedgerBridge:
    """Unified read-only view over both ledger chains.

    Constructed with the paths to both SQLite files. Passing ``None``
    for either path silently omits that chain from results (graceful
    degradation for tests / ephemeral deployments).

    Usage from the operator dashboard::

        bridge = LedgerBridge(
            authority_db=STATE._ledger_path,
            event_db=DATA_DIR / "events.sqlite",
        )
        combined = bridge.tail(limit=50)
    """

    def __init__(
        self,
        authority_db: Path | None = None,
        event_db: Path | None = None,
    ) -> None:
        self._authority_db = authority_db
        self._event_db = event_db

    def authority_entries(
        self, limit: int = 100, offset: int = 0
    ) -> Sequence[BridgedEntry]:
        """Read rows from the governance authority chain."""
        return tuple(_authority_entries(self._authority_db, limit, offset))

    def event_entries(
        self, limit: int = 100, offset: int = 0
    ) -> Sequence[BridgedEntry]:
        """Read rows from the event store chain."""
        return tuple(_event_store_entries(self._event_db, limit, offset))

    def tail(self, limit: int = 100) -> Sequence[BridgedEntry]:
        """Return the most-recent ``limit`` entries across both chains,
        sorted chronologically (ascending ts_utc).

        The merge is a simple in-memory sort; not suitable for very large
        datasets, but ``limit`` keeps the result bounded.
        """
        half = max(limit, 20)
        auth = list(_authority_entries(self._authority_db, half, 0))
        evts = list(_event_store_entries(self._event_db, half, 0))
        combined = sorted(auth + evts, key=lambda e: e.ts_utc)
        return tuple(combined[-limit:])

    def chain_stats(self) -> dict[str, Any]:
        """Return entry counts + availability for both chains."""
        auth_count = 0
        event_count = 0
        if self._authority_db and self._authority_db.exists():
            try:
                import sqlite3

                uri = f"file:{self._authority_db}?mode=ro"
                conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM ledger_authority"
                ).fetchone()
                auth_count = int(row[0]) if row else 0
                conn.close()
            except Exception:  # pragma: no cover
                pass
        if self._event_db and self._event_db.exists():
            try:
                import sqlite3

                uri = f"file:{self._event_db}?mode=ro"
                conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
                row = conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()
                event_count = int(row[0]) if row else 0
                conn.close()
            except Exception:  # pragma: no cover
                pass
        return {
            "authority_chain": {
                "available": bool(self._authority_db and self._authority_db.exists()),
                "entries": auth_count,
                "path": str(self._authority_db) if self._authority_db else None,
            },
            "event_chain": {
                "available": bool(self._event_db and self._event_db.exists()),
                "entries": event_count,
                "path": str(self._event_db) if self._event_db else None,
            },
            "total_entries": auth_count + event_count,
        }


__all__ = ["BridgedEntry", "LedgerBridge"]

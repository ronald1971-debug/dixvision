"""GOV-G17 — Read-only audit replay.

Replays ledger rows in deterministic order and produces a BLAKE2b-128
content digest. Pure function — no I/O (INV-15).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuditRow:
    """Immutable representation of one ledger row."""

    ts_ns: int
    kind: str
    payload: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class AuditReplayReport:
    """Result of a deterministic audit replay."""

    rows: tuple[AuditRow, ...]
    digest: str  # BLAKE2b-128 hex over canonical JSON


def _canonical_json(row: AuditRow) -> bytes:
    """Stable, key-sorted JSON bytes for a single row."""
    doc = {
        "kind": row.kind,
        "payload": row.payload,
        "ts_ns": row.ts_ns,
    }
    return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()


def replay_audit_rows(rows: Sequence[Mapping[str, object]]) -> AuditReplayReport:
    """Validate, sort by ``ts_ns``, and compute a BLAKE2b-128 digest.

    Pure — no I/O. Returns an :class:`AuditReplayReport`.
    """
    parsed: list[AuditRow] = []
    for raw in rows:
        ts_ns = int(raw["ts_ns"])  # type: ignore[arg-type]
        kind = str(raw["kind"])  # type: ignore[arg-type]
        payload: Mapping[str, object] = dict(raw.get("payload") or {})  # type: ignore[arg-type]
        parsed.append(AuditRow(ts_ns=ts_ns, kind=kind, payload=payload))

    sorted_rows = sorted(parsed, key=lambda r: r.ts_ns)

    h = hashlib.blake2b(digest_size=16)
    for row in sorted_rows:
        h.update(_canonical_json(row))

    return AuditReplayReport(rows=tuple(sorted_rows), digest=h.hexdigest())


__all__ = ["AuditRow", "AuditReplayReport", "replay_audit_rows"]

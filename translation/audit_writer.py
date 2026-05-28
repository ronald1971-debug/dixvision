"""DB-14 — audit writer for translation-layer events.

Writes translation audit rows to the authority ledger. This module
is the only place the translation layer touches the ledger — all
other translation modules are pure functions.

B1:     No imports from engine tiers; ledger is accessed via an
        injected callable (dependency-inversion so tests stub it).
B27/B28: Never constructs typed events.
INV-15:  All serialisation is deterministic (sorted keys).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

__all__ = ["AuditWriteResult", "TranslationAuditWriter"]


@dataclass(frozen=True, slots=True)
class AuditWriteResult:
    """Outcome of a single audit-row write."""

    row_kind: str
    digest: str
    ts_ns: int


LedgerSink = Callable[[int, str, dict[str, Any]], None]
"""A callable with signature ``(ts_ns, kind, payload) -> None``."""


class TranslationAuditWriter:
    """Writes translation-layer audit rows via an injected ledger sink.

    The sink has the same signature as
    ``governance_engine.control_plane.LedgerAuthorityWriter.append``
    so the production wiring is a single injection point.
    """

    def __init__(self, sink: LedgerSink) -> None:
        self._sink = sink

    def write_translation(
        self,
        *,
        ts_ns: int,
        intent_id: str,
        patch_payload: dict[str, Any],
        validation_passed: bool,
        detail: str = "",
    ) -> AuditWriteResult:
        """Write a TRANSLATION_AUDIT row."""
        payload: dict[str, Any] = {
            "intent_id": intent_id,
            "content_hash": patch_payload.get("content_hash", ""),
            "strategy_id": patch_payload.get("strategy_id", ""),
            "parameter": patch_payload.get("parameter", ""),
            "validation_passed": validation_passed,
            "detail": detail,
        }
        kind = "TRANSLATION_AUDIT"
        self._sink(ts_ns, kind, payload)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
        digest = hashlib.blake2b(canonical.encode("utf-8"), digest_size=16).hexdigest()
        return AuditWriteResult(row_kind=kind, digest=digest, ts_ns=ts_ns)

    def write_round_trip_failure(
        self,
        *,
        ts_ns: int,
        intent_id: str,
        mismatches: tuple[str, ...],
    ) -> AuditWriteResult:
        """Write a TRANSLATION_ROUND_TRIP_FAILURE row."""
        payload: dict[str, Any] = {
            "intent_id": intent_id,
            "mismatch_count": len(mismatches),
            "mismatches": list(mismatches[:10]),
        }
        kind = "TRANSLATION_ROUND_TRIP_FAILURE"
        self._sink(ts_ns, kind, payload)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
        digest = hashlib.blake2b(canonical.encode("utf-8"), digest_size=16).hexdigest()
        return AuditWriteResult(row_kind=kind, digest=digest, ts_ns=ts_ns)

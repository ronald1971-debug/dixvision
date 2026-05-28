"""translation.audit_log — Translation Audit Engine.

Records every translation event (external payload → canonical contract) with
full provenance. Enables forensic replay of data ingestion, trust score
analysis, and detection of source quality degradation.

Integrates with the authority ledger for immutable recording. All entries
are append-only, hash-chained, and carry governance_origin tags.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum

from system import time_source


class AuditOutcome(StrEnum):
    """Translation audit outcome classification."""

    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    TRUST_REJECTED = "TRUST_REJECTED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"


@dataclass(frozen=True, slots=True)
class TranslationAuditEntry:
    """Single translation audit record."""

    source_platform: str
    output_type: str
    outcome: AuditOutcome
    trust_score: float
    confidence: float
    validation_score: float
    trace_id: str
    latency_ms: float
    ts_ns: int = field(default_factory=time_source.wall_ns)
    errors: tuple[str, ...] = ()
    payload_size_bytes: int = 0


@dataclass(frozen=True, slots=True)
class SourceQualityReport:
    """Aggregated quality report for a single data source."""

    source_platform: str
    total_translations: int
    success_rate: float
    avg_trust_score: float
    avg_confidence: float
    avg_latency_ms: float
    error_rate: float
    last_seen_ns: int


class TranslationAuditLog:
    """Append-only audit log for translation events.

    Maintains a bounded in-memory buffer with periodic flush to the
    authority ledger. Computes per-source quality metrics for the
    governance engine's external_signal_policy.
    """

    __slots__ = ("_buffer", "_max_buffer", "_source_counters")

    def __init__(self, max_buffer: int = 10_000) -> None:
        self._buffer: deque[TranslationAuditEntry] = deque(maxlen=max_buffer)
        self._max_buffer = max_buffer
        self._source_counters: dict[str, dict[str, int | float]] = {}

    def record(self, entry: TranslationAuditEntry) -> None:
        """Append a translation audit entry.

        Updates per-source counters and appends to the ledger.
        """
        self._buffer.append(entry)
        self._update_counters(entry)
        self._emit_to_ledger(entry)

    def record_success(
        self,
        source_platform: str,
        output_type: str,
        *,
        trust_score: float,
        confidence: float,
        latency_ms: float,
        trace_id: str = "",
        payload_size: int = 0,
    ) -> TranslationAuditEntry:
        """Convenience: record a successful translation."""
        entry = TranslationAuditEntry(
            source_platform=source_platform,
            output_type=output_type,
            outcome=AuditOutcome.SUCCESS,
            trust_score=trust_score,
            confidence=confidence,
            validation_score=1.0,
            trace_id=trace_id,
            latency_ms=latency_ms,
            payload_size_bytes=payload_size,
        )
        self.record(entry)
        return entry

    def record_failure(
        self,
        source_platform: str,
        output_type: str,
        outcome: AuditOutcome,
        *,
        errors: tuple[str, ...] = (),
        trace_id: str = "",
        latency_ms: float = 0.0,
    ) -> TranslationAuditEntry:
        """Convenience: record a failed translation."""
        entry = TranslationAuditEntry(
            source_platform=source_platform,
            output_type=output_type,
            outcome=outcome,
            trust_score=0.0,
            confidence=0.0,
            validation_score=0.0,
            trace_id=trace_id,
            latency_ms=latency_ms,
            errors=errors,
        )
        self.record(entry)
        return entry

    def get_source_report(self, source_platform: str) -> SourceQualityReport | None:
        """Compute quality report for a specific source."""
        counters = self._source_counters.get(source_platform)
        if not counters:
            return None

        total = int(counters.get("total", 0))
        if total == 0:
            return None

        successes = int(counters.get("successes", 0))
        errors = int(counters.get("errors", 0))

        return SourceQualityReport(
            source_platform=source_platform,
            total_translations=total,
            success_rate=successes / total if total else 0.0,
            avg_trust_score=counters.get("sum_trust", 0.0) / total,
            avg_confidence=counters.get("sum_confidence", 0.0) / total,
            avg_latency_ms=counters.get("sum_latency", 0.0) / total,
            error_rate=errors / total if total else 0.0,
            last_seen_ns=int(counters.get("last_seen_ns", 0)),
        )

    def get_all_source_reports(self) -> list[SourceQualityReport]:
        """Compute quality reports for all known sources."""
        reports = []
        for source in self._source_counters:
            report = self.get_source_report(source)
            if report:
                reports.append(report)
        return sorted(reports, key=lambda r: r.success_rate)

    def get_recent_entries(
        self, *, limit: int = 100, source: str = ""
    ) -> list[TranslationAuditEntry]:
        """Retrieve recent audit entries, optionally filtered by source."""
        entries = list(self._buffer)
        if source:
            entries = [e for e in entries if e.source_platform == source]
        return entries[-limit:]

    def _update_counters(self, entry: TranslationAuditEntry) -> None:
        """Update per-source aggregation counters."""
        src = entry.source_platform
        if src not in self._source_counters:
            self._source_counters[src] = {
                "total": 0,
                "successes": 0,
                "errors": 0,
                "sum_trust": 0.0,
                "sum_confidence": 0.0,
                "sum_latency": 0.0,
                "last_seen_ns": 0,
            }
        c = self._source_counters[src]
        c["total"] = int(c["total"]) + 1
        c["last_seen_ns"] = entry.ts_ns
        c["sum_latency"] = float(c["sum_latency"]) + entry.latency_ms

        if entry.outcome == AuditOutcome.SUCCESS:
            c["successes"] = int(c["successes"]) + 1
            c["sum_trust"] = float(c["sum_trust"]) + entry.trust_score
            c["sum_confidence"] = float(c["sum_confidence"]) + entry.confidence
        else:
            c["errors"] = int(c["errors"]) + 1

    def _emit_to_ledger(self, entry: TranslationAuditEntry) -> None:
        """Emit entry to the authority ledger (best-effort)."""
        try:
            from state.ledger.event_store import append_event

            append_event(
                "TRANSLATION",
                entry.outcome.value,
                entry.source_platform,
                {
                    "output_type": entry.output_type,
                    "trust_score": entry.trust_score,
                    "confidence": entry.confidence,
                    "trace_id": entry.trace_id,
                    "latency_ms": entry.latency_ms,
                },
            )
        except Exception:
            pass

    @property
    def total_entries(self) -> int:
        """Total entries in the buffer."""
        return len(self._buffer)


# Module-level singleton
_AUDIT_LOG: TranslationAuditLog | None = None


def get_translation_audit_log() -> TranslationAuditLog:
    """Get or create the singleton TranslationAuditLog."""
    global _AUDIT_LOG
    if _AUDIT_LOG is None:
        _AUDIT_LOG = TranslationAuditLog()
    return _AUDIT_LOG


__all__ = [
    "AuditOutcome",
    "SourceQualityReport",
    "TranslationAuditEntry",
    "TranslationAuditLog",
    "get_translation_audit_log",
]

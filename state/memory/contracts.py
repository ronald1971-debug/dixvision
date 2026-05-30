"""state.memory.contracts — Unified Cognitive Memory Layer value types.

Pure data surface. No engine imports, no IO, no clock (INV-15, INV-08).
All records are frozen+slotted for structural hashing and audit integrity.
"""

from __future__ import annotations

import dataclasses
import enum
from types import MappingProxyType
from typing import Any, Mapping


class MemoryKind(str, enum.Enum):
    """Semantic category of a MemoryRecord."""

    EPISODIC   = "EPISODIC"    # lived experience — thought, observation, tick
    SEMANTIC   = "SEMANTIC"    # abstracted knowledge — belief, pattern, insight
    PROCEDURAL = "PROCEDURAL"  # how-to — action-outcome sequences, repair plans
    STRATEGY   = "STRATEGY"    # strategy proposals, mutations, fitness outcomes
    TRADER     = "TRADER"      # trader archetype performance, regime history
    GOVERNANCE = "GOVERNANCE"  # mode transitions, violations, operator actions
    RUNTIME    = "RUNTIME"     # health events, failures, recovery, diagnostics
    REGRET     = "REGRET"      # counterfactual — missed, early-exit, oversized


@dataclasses.dataclass(frozen=True, slots=True)
class MemoryRecord:
    """Single unit of cognitive memory — the universal record type.

    All stores in the Unified Cognitive Memory Layer accept and emit
    MemoryRecord. Domain stores may attach structured data in ``body``.

    Fields:
        record_id:  stable opaque identifier (set by MemoryIdentitySystem).
        kind:       semantic category.
        ts_ns:      nanosecond timestamp of the originating event
                    (caller-supplied — never wall-clock inside stores).
        source:     dotted module or subsystem that produced this record.
        summary:    human-readable one-line description (for operator UI).
        body:       arbitrary key→str payload (stringified at boundary).
        tags:       frozenset of keyword tags for inverted index.
        confidence: 0.0–1.0 producer confidence; -1.0 = not applicable.
        parent_id:  record_id of the record this derives from (lineage).
    """

    record_id:  str
    kind:       MemoryKind
    ts_ns:      int
    source:     str
    summary:    str
    body:       Mapping[str, str]                  = dataclasses.field(default_factory=lambda: MappingProxyType({}))
    tags:       frozenset[str]                     = dataclasses.field(default_factory=frozenset)
    confidence: float                              = -1.0
    parent_id:  str | None                        = None

    def __post_init__(self) -> None:
        if not self.record_id:
            raise ValueError("MemoryRecord.record_id must be non-empty")
        if self.ts_ns <= 0:
            raise ValueError(f"MemoryRecord.ts_ns must be positive, got {self.ts_ns!r}")
        if not self.source:
            raise ValueError("MemoryRecord.source must be non-empty")
        if not isinstance(self.body, MappingProxyType):
            object.__setattr__(self, "body", MappingProxyType(dict(self.body)))
        if not isinstance(self.confidence, float):
            object.__setattr__(self, "confidence", float(self.confidence))

    @property
    def age_ns(self) -> int:
        """Nanoseconds since this record was created (not replay-safe; informational only)."""
        from system.time_source import wall_ns
        return wall_ns() - self.ts_ns


@dataclasses.dataclass(frozen=True, slots=True)
class MemoryQuery:
    """Cross-store search request for the Unified Cognitive Memory Layer."""

    query_id:   str
    ts_ns:      int
    kinds:      frozenset[MemoryKind]   = dataclasses.field(default_factory=frozenset)
    keywords:   tuple[str, ...]         = ()
    source:     str | None              = None
    since_ns:   int | None             = None
    until_ns:   int | None             = None
    limit:      int                     = 20

    def __post_init__(self) -> None:
        if not self.query_id:
            raise ValueError("MemoryQuery.query_id must be non-empty")
        if self.ts_ns <= 0:
            raise ValueError(f"MemoryQuery.ts_ns must be positive, got {self.ts_ns!r}")
        if self.limit <= 0:
            raise ValueError(f"MemoryQuery.limit must be positive, got {self.limit!r}")


@dataclasses.dataclass(frozen=True, slots=True)
class MemorySearchResult:
    """Response from a cross-store query."""

    query_id: str
    ts_ns:    int
    records:  tuple[MemoryRecord, ...]
    total:    int


__all__ = [
    "MemoryKind",
    "MemoryRecord",
    "MemoryQuery",
    "MemorySearchResult",
]

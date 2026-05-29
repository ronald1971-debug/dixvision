"""runtime.unified_fabric.contracts — Unified Event Fabric value types.

Pure data layer — no engine imports, no clock, no IO (INV-15, INV-08).
All records are frozen+slotted for structural hashing and replay parity.

FabricDomain: which subsystem originated an event (14 domains).
UnifiedEvent:  single universal event record wrapping any domain event.
CausalLink:   one directed causal edge (cause_id → effect_id).
TraceSpan:    one span in a cross-event trace tree.
"""

from __future__ import annotations

import dataclasses
import enum
from types import MappingProxyType
from typing import Any, Mapping


class FabricDomain(str, enum.Enum):
    """Originating subsystem domain for a UnifiedEvent."""

    COGNITIVE  = "COGNITIVE"    # CognitiveEventBus (INDIRA thoughts, DYON violations)
    GOVERNANCE = "GOVERNANCE"   # Mode transitions, operator overrides, cogov decisions
    EXECUTION  = "EXECUTION"    # Fill events, order routing, execution intents
    MARKET     = "MARKET"       # Price ticks, OHLCV, order book, funding
    SIMULATION = "SIMULATION"   # Backtest events, mutation tournaments, regime tests
    LEARNING   = "LEARNING"     # LearningUpdate, strategy mutations, reward signals
    TELEMETRY  = "TELEMETRY"    # Metrics, spans, health gauges, aggregator samples
    SYSTEM     = "SYSTEM"       # Health reports, boot/shutdown, hazard emissions
    MEMORY     = "MEMORY"       # Memory writes (Stage 4 unified layer)
    EVOLUTION  = "EVOLUTION"    # Patch proposals, genome mutations, evolution stages
    RESEARCH   = "RESEARCH"     # Browser research, external data ingestion
    UI         = "UI"           # Operator commands, dashboard interactions
    AUDIT      = "AUDIT"        # Compliance, authority decisions, HMAC-signed ops
    UNKNOWN    = "UNKNOWN"      # Unclassified/bridged from external system


class FabricPriority(int, enum.Enum):
    """Delivery priority — lower number = higher priority."""

    CRITICAL = 0   # Kill switch, governance block — must deliver synchronously
    HIGH     = 1   # DYON violation, INDIRA breach — deliver in current tick
    NORMAL   = 2   # Regular cognitive/market — best-effort ordered
    LOW      = 3   # Telemetry, audit — background


@dataclasses.dataclass(frozen=True, slots=True)
class UnifiedEvent:
    """Universal event record traversing the Unified Event Fabric.

    Every event emitted by any subsystem is wrapped in a UnifiedEvent
    before entering the fabric. Existing typed events (FabricEvent,
    CognitiveChannel payloads) are carried in ``payload``; the fabric
    adds tracing, lineage, sequencing, and domain tagging.

    Fields:
        event_id:    SHA-256-based stable unique id (assigned by CentralBusAuthority).
        domain:      originating subsystem (FabricDomain).
        event_type:  string sub-type within the domain (e.g. "INDIRA_THOUGHT").
        ts_ns:       nanosecond timestamp — ALWAYS caller-supplied (INV-15).
        source:      dotted module path of the emitter.
        payload:     domain-specific payload (frozen mapping, str→Any stringified).
        priority:    delivery priority.
        sequence:    global monotonic sequence number (assigned by fabric).
        trace_id:    span group identifier (propagated across causal chains).
        parent_id:   event_id of the parent event (causality; "" = root).
        tags:        frozenset of keyword tags for indexing and filtering.
    """

    event_id:   str
    domain:     FabricDomain
    event_type: str
    ts_ns:      int
    source:     str
    payload:    Mapping[str, Any]
    priority:   FabricPriority = FabricPriority.NORMAL
    sequence:   int            = 0
    trace_id:   str            = ""
    parent_id:  str            = ""
    tags:       frozenset[str] = dataclasses.field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("UnifiedEvent.event_id must be non-empty")
        if self.ts_ns <= 0:
            raise ValueError(f"UnifiedEvent.ts_ns must be positive, got {self.ts_ns!r}")
        if not self.source:
            raise ValueError("UnifiedEvent.source must be non-empty")
        if not isinstance(self.payload, MappingProxyType):
            object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))

    @property
    def is_root(self) -> bool:
        return not self.parent_id

    @property
    def has_trace(self) -> bool:
        return bool(self.trace_id)


@dataclasses.dataclass(frozen=True, slots=True)
class CausalLink:
    """Directed causal edge: cause_id → effect_id.

    Stored in EventLineageGraph. The fabric records a CausalLink
    whenever one event provably causes another (e.g. DYON_VIOLATION
    causes an INDIRA confidence adjustment, a RISK_BREACH causes a
    GOVERNANCE mode transition).
    """

    cause_id:   str       # parent event_id
    effect_id:  str       # child event_id
    ts_ns:      int       # when the link was recorded (INV-15)
    kind:       str = ""  # optional label: "triggers", "informs", "blocks"


@dataclasses.dataclass(frozen=True, slots=True)
class TraceSpan:
    """One span in a distributed trace across the event fabric.

    Spans share a trace_id. The fabric creates a root span when a new
    trace_id first appears and child spans for each propagated event.
    """

    span_id:    str
    trace_id:   str
    parent_span_id: str  # "" = root span
    event_id:   str
    domain:     FabricDomain
    event_type: str
    ts_ns:      int
    source:     str


__all__ = [
    "FabricDomain",
    "FabricPriority",
    "UnifiedEvent",
    "CausalLink",
    "TraceSpan",
]

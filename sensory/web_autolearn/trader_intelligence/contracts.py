"""Value types for the Trader Intelligence Pipeline.

All types are frozen + slotted dataclasses — hashable, immutable,
ledger-safe (INV-15).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SourceCategory(StrEnum):
    """Diversity category for trader sources."""

    DISCRETIONARY = "DISCRETIONARY"
    QUANT = "QUANT"
    MACRO = "MACRO"
    CRYPTO_NATIVE = "CRYPTO_NATIVE"
    HFT = "HFT"
    MARKET_MAKER = "MARKET_MAKER"
    ALGORITHMIC = "ALGORITHMIC"
    INSTITUTIONAL = "INSTITUTIONAL"
    RETAIL = "RETAIL"


class SourceMedium(StrEnum):
    """Medium through which trader intelligence is collected."""

    SOCIAL_POST = "SOCIAL_POST"
    ARTICLE = "ARTICLE"
    INTERVIEW = "INTERVIEW"
    TRADE_LOG = "TRADE_LOG"
    ON_CHAIN = "ON_CHAIN"
    ORDER_FLOW = "ORDER_FLOW"
    RESEARCH_NOTE = "RESEARCH_NOTE"
    BOOK = "BOOK"
    FORUM = "FORUM"
    PODCAST = "PODCAST"


@dataclass(frozen=True, slots=True)
class TraderSource:
    """A registered trader intelligence source.

    Each source maps to one or more trader identities and carries
    metadata for credibility scoring and diversity tracking.
    """

    source_id: str
    name: str
    category: SourceCategory
    medium: SourceMedium
    url_pattern: str = ""
    credibility_weight: float = 0.5
    active: bool = True
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source_id:
            raise ValueError("source_id must be non-empty")
        if not 0.0 <= self.credibility_weight <= 1.0:
            raise ValueError("credibility_weight must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class TraderPattern:
    """Extracted and encoded trader behavioral pattern.

    This is the pipeline's output: a structured, auditable, abstracted
    pattern ready for validation and knowledge store ingestion.

    NOT a raw strategy copy — an abstracted decision framework.
    """

    pattern_id: str
    source_trader_id: str
    source_category: SourceCategory
    strategy_type: str
    entry_logic: str
    exit_logic: str
    risk_model: str
    context_conditions: tuple[str, ...]
    confidence: float
    credibility_score: float
    embedding: tuple[float, ...] = ()
    decay_weight: float = 1.0
    ts_ns: int = 0
    version: int = 1
    outcome_pnl: float | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.pattern_id:
            raise ValueError("pattern_id must be non-empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """Result of running the full Trader Intelligence Pipeline."""

    patterns_extracted: int
    patterns_accepted: int
    patterns_rejected: int
    sources_processed: int
    credibility_filtered: int
    validation_failures: int
    elapsed_ns: int
    errors: tuple[str, ...] = ()

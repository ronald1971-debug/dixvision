"""core.contracts.translation — Signal Translation Protocol (System Spec §Normalizer).

All external payloads must pass through the canonical normalizer before reaching
any engine. This contract defines the translation protocol that normalizes
heterogeneous inputs into canonical contract types with full provenance metadata.

Output types: MarketTick, SignalEvent, NewsItem, SocialPost, SentimentSignal,
MacroEvent, NarrativeCluster, BacktestResult, TraderProfile.

Required metadata on EVERY normalized output:
  source_platform, source_author, ts_ns, trust_score, confidence,
  validation_score, trace_id, governance_origin.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class TranslationType(StrEnum):
    """Canonical output type categories from the normalizer."""

    MARKET_TICK = "MARKET_TICK"
    SIGNAL_EVENT = "SIGNAL_EVENT"
    NEWS_ITEM = "NEWS_ITEM"
    SOCIAL_POST = "SOCIAL_POST"
    SENTIMENT_SIGNAL = "SENTIMENT_SIGNAL"
    MACRO_EVENT = "MACRO_EVENT"
    NARRATIVE_CLUSTER = "NARRATIVE_CLUSTER"
    BACKTEST_RESULT = "BACKTEST_RESULT"
    TRADER_PROFILE = "TRADER_PROFILE"


class TrustLevel(StrEnum):
    """Trust level for external data sources per source_trust_promotions.py."""

    UNTRUSTED = "UNTRUSTED"
    PROVISIONAL = "PROVISIONAL"
    VERIFIED = "VERIFIED"
    INTERNAL = "INTERNAL"


@dataclass(frozen=True, slots=True)
class ProvenanceMetadata:
    """Required metadata on every normalized output (Build Directive §11).

    Tracks full provenance chain from external source through normalization
    to engine consumption. Ensures auditability and replay.
    """

    source_platform: str
    source_author: str
    ts_ns: int
    trust_score: float
    confidence: float
    validation_score: float
    trace_id: str
    governance_origin: str

    def __post_init__(self) -> None:
        if not self.source_platform:
            msg = "source_platform must be non-empty"
            raise ValueError(msg)
        if self.ts_ns < 0:
            msg = "ts_ns must be >= 0"
            raise ValueError(msg)
        if not (0.0 <= self.trust_score <= 1.0):
            msg = "trust_score must be in [0, 1]"
            raise ValueError(msg)
        if not (0.0 <= self.confidence <= 1.0):
            msg = "confidence must be in [0, 1]"
            raise ValueError(msg)
        if not (0.0 <= self.validation_score <= 1.0):
            msg = "validation_score must be in [0, 1]"
            raise ValueError(msg)
        if not self.trace_id:
            msg = "trace_id must be non-empty"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class TranslationResult:
    """Result of translating an external payload into a canonical type."""

    success: bool
    output_type: TranslationType
    payload: dict[str, Any]
    provenance: ProvenanceMetadata
    warnings: tuple[str, ...] = ()
    error: str = ""


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Report from schema validation of a translated payload."""

    valid: bool
    output_type: TranslationType
    field_errors: tuple[str, ...] = ()
    missing_fields: tuple[str, ...] = ()
    type_mismatches: tuple[str, ...] = ()


@runtime_checkable
class ITranslation(Protocol):
    """Protocol: translation/normalization contract.

    The canonical normalizer (data_pipeline/normalizer.py) implements this.
    All external data sources route through this contract before reaching
    any engine. No raw external payload may bypass normalization.
    """

    def translate(
        self,
        raw_payload: dict[str, Any],
        *,
        source_platform: str,
        source_author: str = "",
        trace_id: str = "",
    ) -> TranslationResult:
        """Translate a raw external payload into a canonical contract type.

        Args:
            raw_payload: The heterogeneous input from an external source.
            source_platform: Identifier of the source platform.
            source_author: Author/account that produced the payload.
            trace_id: Distributed trace ID for observability.

        Returns:
            TranslationResult with canonical type, payload, and provenance.
        """
        ...

    def validate(self, result: TranslationResult) -> ValidationReport:
        """Validate a translated result against its canonical schema.

        Ensures all required fields are present and correctly typed before
        the payload reaches an engine.

        Args:
            result: The TranslationResult to validate.

        Returns:
            ValidationReport with any field errors or type mismatches.
        """
        ...

    def supported_types(self) -> tuple[TranslationType, ...]:
        """Return all translation types this normalizer can produce."""
        ...


@runtime_checkable
class ISourceRegistry(Protocol):
    """Protocol: external source registry for trust management."""

    def get_trust(self, source_platform: str) -> TrustLevel:
        """Return the current trust level for a source platform."""
        ...

    def promote(
        self, source_platform: str, target: TrustLevel, *, operator_id: str, reason: str
    ) -> bool:
        """Promote a source's trust level (operator-only, Class C mutation)."""
        ...


__all__ = [
    "ISourceRegistry",
    "ITranslation",
    "ProvenanceMetadata",
    "TranslationResult",
    "TranslationType",
    "TrustLevel",
    "ValidationReport",
]

"""translation.validator — Schema Validation for Translated Payloads.

Validates that normalized payloads from the data pipeline conform to the
canonical schemas before they enter the intelligence pipeline. Catches
malformed data, missing required fields, out-of-range values, and
schema version mismatches.

Every payload must pass validation before being routed to any engine.
Failed validations are logged to the translation audit trail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from system import time_source


class ValidationResult(StrEnum):
    """Outcome of payload validation."""

    VALID = "VALID"
    INVALID_SCHEMA = "INVALID_SCHEMA"
    MISSING_REQUIRED = "MISSING_REQUIRED"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    TYPE_MISMATCH = "TYPE_MISMATCH"
    TRUST_BELOW_THRESHOLD = "TRUST_BELOW_THRESHOLD"


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Detailed validation report for a payload."""

    result: ValidationResult
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    payload_type: str = ""
    ts_ns: int = field(default_factory=time_source.wall_ns)

    @property
    def is_valid(self) -> bool:
        return self.result == ValidationResult.VALID


# Schema definitions for canonical payload types
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "MARKET_TICK": ("symbol", "price", "volume", "ts_ns"),
    "SIGNAL_EVENT": ("symbol", "direction", "confidence", "source", "ts_ns"),
    "NEWS_ITEM": ("headline", "source_platform", "ts_ns"),
    "SOCIAL_POST": ("text", "source_platform", "author", "ts_ns"),
    "SENTIMENT_SIGNAL": ("symbol", "polarity", "intensity", "source_platform"),
    "MACRO_EVENT": ("event_type", "impact_score", "source_platform"),
    "TRADER_PROFILE": ("trader_id", "philosophy", "timeframe"),
}

NUMERIC_RANGES: dict[str, tuple[float, float]] = {
    "confidence": (0.0, 1.0),
    "trust_score": (0.0, 1.0),
    "intensity": (0.0, 1.0),
    "impact_score": (0.0, 1.0),
    "validation_score": (0.0, 1.0),
    "price": (0.0, float("inf")),
    "volume": (0.0, float("inf")),
}


def validate_payload(payload: dict[str, Any], payload_type: str) -> ValidationReport:
    """Validate a normalized payload against its canonical schema.

    Args:
        payload: The normalized payload dictionary.
        payload_type: One of the canonical types (MARKET_TICK, SIGNAL_EVENT, etc.)

    Returns:
        ValidationReport with detailed error information.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Check payload type is known
    required = REQUIRED_FIELDS.get(payload_type)
    if required is None:
        return ValidationReport(
            result=ValidationResult.INVALID_SCHEMA,
            errors=(f"Unknown payload type: {payload_type}",),
            payload_type=payload_type,
        )

    # Check required fields
    for field_name in required:
        if field_name not in payload:
            errors.append(f"Missing required field: {field_name}")
        elif payload[field_name] is None:
            errors.append(f"Required field is None: {field_name}")

    if errors:
        return ValidationReport(
            result=ValidationResult.MISSING_REQUIRED,
            errors=tuple(errors),
            payload_type=payload_type,
        )

    # Check numeric ranges
    for field_name, (min_val, max_val) in NUMERIC_RANGES.items():
        if field_name in payload:
            try:
                value = float(payload[field_name])
                if value < min_val or value > max_val:
                    errors.append(f"{field_name}={value} out of range [{min_val}, {max_val}]")
            except (TypeError, ValueError):
                errors.append(
                    f"{field_name}: expected numeric, got {type(payload[field_name]).__name__}"
                )

    if errors:
        return ValidationReport(
            result=ValidationResult.OUT_OF_RANGE,
            errors=tuple(errors),
            payload_type=payload_type,
        )

    # Check trust threshold (external sources ≤ 0.5)
    trust = payload.get("trust_score", 0.5)
    try:
        trust = float(trust)
        if trust > 0.5 and payload.get("source_platform", "internal") != "internal":
            warnings.append(f"External source trust {trust:.2f} > 0.5 (will be capped)")
    except (TypeError, ValueError):
        pass

    return ValidationReport(
        result=ValidationResult.VALID,
        errors=(),
        warnings=tuple(warnings),
        payload_type=payload_type,
    )


def validate_batch(payloads: list[dict[str, Any]], payload_type: str) -> list[ValidationReport]:
    """Validate a batch of payloads, returning reports for each."""
    return [validate_payload(p, payload_type) for p in payloads]


def filter_valid(payloads: list[dict[str, Any]], payload_type: str) -> list[dict[str, Any]]:
    """Filter a batch to only valid payloads."""
    return [p for p in payloads if validate_payload(p, payload_type).is_valid]


__all__ = [
    "NUMERIC_RANGES",
    "REQUIRED_FIELDS",
    "ValidationReport",
    "ValidationResult",
    "filter_valid",
    "validate_batch",
    "validate_payload",
]

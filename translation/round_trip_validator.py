"""CORE-15 — round-trip translation validator.

Validates that translating an intent → patch payload → back to
an intent-equivalent shape preserves all semantic fields (INV-15).
Pure function; no I/O, no side effects.

B1:     No imports from engine tiers.
INV-15: Pure function of inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["RoundTripResult", "validate_round_trip"]


@dataclass(frozen=True, slots=True)
class RoundTripResult:
    """Outcome of a round-trip validation."""

    passed: bool
    mismatches: tuple[str, ...]
    detail: str


_REQUIRED_FIELDS = (
    "intent_id",
    "strategy_id",
    "parameter",
    "old_value",
    "new_value",
    "reason",
    "ts_ns",
    "source",
    "content_hash",
)


def validate_round_trip(
    original: dict[str, Any],
    translated: dict[str, Any],
) -> RoundTripResult:
    """Compare ``original`` and ``translated`` payload dicts field-by-field.

    Checks that all required fields are present in ``translated`` and
    that value-preserving fields are byte-identical after round-trip.
    """
    mismatches: list[str] = []

    # Required-field presence check.
    for field in _REQUIRED_FIELDS:
        if field not in translated:
            mismatches.append(f"missing:{field}")

    # Value-identity check for scalar fields (excluding meta).
    for field in ("strategy_id", "parameter", "old_value", "new_value", "reason", "ts_ns"):
        if field in original and field in translated:
            if original[field] != translated[field]:
                mismatches.append(
                    f"mismatch:{field}:{original[field]!r}!={translated[field]!r}"
                )

    passed = len(mismatches) == 0
    return RoundTripResult(
        passed=passed,
        mismatches=tuple(mismatches),
        detail="OK" if passed else f"{len(mismatches)} mismatch(es): {', '.join(mismatches[:3])}",
    )

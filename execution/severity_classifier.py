"""EXEC-06 — event severity classification and routing recommendation.

Pure functions. No I/O, no side effects, no state.

B1:       No imports from engine tiers.
B27/B28:  Never constructs typed events.
INV-15:   All functions are pure — identical inputs produce identical output.
"""

from __future__ import annotations

from typing import Final

from core.contracts.events import HazardEvent, HazardSeverity

__all__ = [
    "SeverityClass",
    "RoutingAction",
    "classify",
    "recommended_action",
    "is_halt_condition",
    "is_safe_mode_condition",
]

_HALT_SEVERITIES: Final[frozenset[HazardSeverity]] = frozenset(
    {HazardSeverity.CRITICAL}
)
_SAFE_MODE_SEVERITIES: Final[frozenset[HazardSeverity]] = frozenset(
    {HazardSeverity.HIGH, HazardSeverity.CRITICAL}
)

# Hazard codes whose presence forces CRITICAL regardless of emitter severity.
_FORCE_CRITICAL_CODES: Final[frozenset[str]] = frozenset(
    {
        "HAZ-DATA-CORRUPTION",
        "HAZ-LEDGER-INCONSISTENCY",
        "HAZ-KILL-SWITCH",
    }
)


class SeverityClass(str):
    """Normalised severity string returned by :func:`classify`."""


class RoutingAction(str):
    """Recommended governance action string."""


def classify(event: HazardEvent) -> HazardSeverity:
    """Return the effective severity of a hazard event.

    Certain hazard codes are promoted to CRITICAL regardless of the
    severity the emitter assigned — data-corruption and ledger
    inconsistency are always critical.
    """
    if event.code in _FORCE_CRITICAL_CODES:
        return HazardSeverity.CRITICAL
    return event.severity


def recommended_action(event: HazardEvent) -> str:
    """Return a recommended governance action string for a hazard event."""
    effective = classify(event)
    if effective is HazardSeverity.CRITICAL:
        return "HALT_AND_LOCK"
    if effective is HazardSeverity.HIGH:
        return "ENTER_SAFE_MODE"
    if effective is HazardSeverity.MEDIUM:
        return "REDUCE_EXPOSURE"
    if effective is HazardSeverity.LOW:
        return "OBSERVE"
    return "OBSERVE"


def is_halt_condition(event: HazardEvent) -> bool:
    """True if the event warrants a full trading halt."""
    return classify(event) in _HALT_SEVERITIES


def is_safe_mode_condition(event: HazardEvent) -> bool:
    """True if the event warrants entering safe mode."""
    return classify(event) in _SAFE_MODE_SEVERITIES

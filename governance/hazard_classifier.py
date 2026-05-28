"""governance.hazard_classifier — Hazard Classification Engine.

Build Plan §5.2: Classifies incoming hazard events by domain, impact,
and urgency to support deterministic routing decisions.
"""

from __future__ import annotations

from dataclasses import dataclass

_MARKET_HAZARDS = frozenset(
    {
        "EXCHANGE_TIMEOUT",
        "FEED_SILENCE",
        "BAD_QUOTE",
        "EXECUTION_LATENCY_SPIKE",
        "API_CONNECTIVITY_FAILURE",
    }
)

_SYSTEM_HAZARDS = frozenset(
    {
        "MEMORY_PRESSURE",
        "CPU_OVERLOAD",
        "SYSTEM_DEGRADATION",
        "HEARTBEAT_TIMEOUT",
    }
)

_INTEGRITY_HAZARDS = frozenset(
    {
        "DATA_CORRUPTION_SUSPECTED",
        "LEDGER_INCONSISTENCY",
        "INTEGRITY_BREACH",
    }
)


@dataclass(frozen=True, slots=True)
class HazardClassification:
    domain: str  # MARKET | SYSTEM | INTEGRITY | UNKNOWN
    urgency: str  # IMMEDIATE | DEFERRED | INFORMATIONAL
    impact: str  # TRADING | INFRASTRUCTURE | DATA | MIXED


def classify(hazard_type: str, severity: str) -> HazardClassification:
    """Classify a hazard by domain, urgency and impact."""
    if hazard_type in _INTEGRITY_HAZARDS:
        return HazardClassification(
            domain="INTEGRITY",
            urgency="IMMEDIATE",
            impact="DATA",
        )
    if hazard_type in _MARKET_HAZARDS:
        urgency = "IMMEDIATE" if severity in {"HIGH", "CRITICAL"} else "DEFERRED"
        return HazardClassification(
            domain="MARKET",
            urgency=urgency,
            impact="TRADING",
        )
    if hazard_type in _SYSTEM_HAZARDS:
        urgency = "IMMEDIATE" if severity == "CRITICAL" else "DEFERRED"
        return HazardClassification(
            domain="SYSTEM",
            urgency=urgency,
            impact="INFRASTRUCTURE",
        )
    return HazardClassification(
        domain="UNKNOWN",
        urgency="DEFERRED",
        impact="MIXED",
    )

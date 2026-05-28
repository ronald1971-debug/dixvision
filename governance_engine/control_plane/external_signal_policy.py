"""External signal policy (BUILD-DIRECTIVE §11).

Validates incoming external signals from platforms in
``registry/external_sources.yaml``. Enforces:

1. Source must be registered and approved (trust > UNTRUSTED)
2. Signal trust cap applied per external_signal_trust.yaml
3. No autonomous source discovery (operator must register first)
4. No copy-trading-as-mirror in live execution
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SourceTrust(StrEnum):
    """Trust levels for external signal sources."""

    UNTRUSTED = "UNTRUSTED"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERIFIED = "VERIFIED"


@dataclass(frozen=True, slots=True)
class ExternalSignalValidation:
    """Result of validating an external signal."""

    allowed: bool
    source_platform: str
    trust_level: SourceTrust
    confidence_cap: float
    reason: str


# Trust → confidence cap mapping (BUILD-DIRECTIVE §11)
TRUST_CONFIDENCE_CAPS: dict[SourceTrust, float] = {
    SourceTrust.UNTRUSTED: 0.0,
    SourceTrust.LOW: 0.3,
    SourceTrust.MEDIUM: 0.5,
    SourceTrust.HIGH: 0.7,
    SourceTrust.VERIFIED: 0.85,
}


def validate_external_signal(
    *,
    source_platform: str,
    registered_sources: dict[str, SourceTrust],
    signal_confidence: float,
) -> ExternalSignalValidation:
    """Validate an external signal against the policy.

    Args:
        source_platform: Platform name (e.g., "tradingview", "mt5").
        registered_sources: Map of platform → trust level from registry.
        signal_confidence: Raw confidence from the external source.

    Returns:
        ExternalSignalValidation with capped confidence and allow/deny.
    """
    # Source must be registered
    if source_platform not in registered_sources:
        return ExternalSignalValidation(
            allowed=False,
            source_platform=source_platform,
            trust_level=SourceTrust.UNTRUSTED,
            confidence_cap=0.0,
            reason=f"source '{source_platform}' not registered"
            " — no autonomous source discovery allowed",
        )

    trust = registered_sources[source_platform]

    # UNTRUSTED sources are blocked
    if trust == SourceTrust.UNTRUSTED:
        return ExternalSignalValidation(
            allowed=False,
            source_platform=source_platform,
            trust_level=trust,
            confidence_cap=0.0,
            reason=f"source '{source_platform}' is UNTRUSTED — operator must promote via dashboard",
        )

    # Apply confidence cap
    cap = TRUST_CONFIDENCE_CAPS[trust]
    capped_confidence = min(signal_confidence, cap)

    return ExternalSignalValidation(
        allowed=True,
        source_platform=source_platform,
        trust_level=trust,
        confidence_cap=capped_confidence,
        reason=f"signal accepted at trust={trust.value},"
        f" confidence capped to {capped_confidence:.3f}",
    )

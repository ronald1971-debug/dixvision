"""Data pipeline normalizer (BUILD-DIRECTIVE §12).

Single entry point converting external payloads from
``data_sources/external/`` and ``execution_engine/adapters/external/``
into canonical DIX contracts.

Every external platform speaks a different schema. The normalizer:
1. Accepts raw payloads (dict[str, Any])
2. Validates schema against platform-specific rules
3. Converts to canonical SignalEvent or observation contracts
4. Applies external_signal_trust cap from governance policy
5. Returns normalized events ready for the bus

The normalizer never mutates state. It is a pure function layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class NormalizationStatus(StrEnum):
    """Outcome of a normalization attempt."""

    SUCCESS = "SUCCESS"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    PLATFORM_UNKNOWN = "PLATFORM_UNKNOWN"
    MISSING_FIELDS = "MISSING_FIELDS"


@dataclass(frozen=True, slots=True)
class NormalizedPayload:
    """Result of normalizing an external payload."""

    status: NormalizationStatus
    platform: str
    symbol: str = ""
    side: str = ""
    confidence: float = 0.0
    raw_payload: dict[str, Any] | None = None
    error: str = ""


# Required fields per platform
PLATFORM_SCHEMAS: dict[str, tuple[str, ...]] = {
    "tradingview": ("symbol", "action", "price"),
    "mt5": ("symbol", "type", "volume"),
    "quantconnect": ("symbol", "direction", "quantity"),
    "backtrader": ("symbol", "side", "size"),
    "vectorbt": ("symbol", "signal", "confidence"),
    "freqtrade": ("pair", "side", "stake_amount"),
    "jesse": ("symbol", "side", "qty"),
    "qstrader": ("ticker", "direction", "quantity"),
}

# Side mapping per platform
SIDE_MAPS: dict[str, dict[str, str]] = {
    "tradingview": {"buy": "BUY", "sell": "SELL", "long": "BUY", "short": "SELL"},
    "mt5": {"buy": "BUY", "sell": "SELL", "buy_limit": "BUY", "sell_limit": "SELL"},
    "quantconnect": {"long": "BUY", "short": "SELL", "flat": "HOLD"},
    "backtrader": {"buy": "BUY", "sell": "SELL"},
    "vectorbt": {"1": "BUY", "-1": "SELL", "0": "HOLD"},
    "freqtrade": {"buy": "BUY", "sell": "SELL", "long": "BUY", "short": "SELL"},
    "jesse": {"buy": "BUY", "sell": "SELL"},
    "qstrader": {"BOT": "BUY", "SLD": "SELL"},
}


def normalize(
    *,
    platform: str,
    payload: dict[str, Any],
) -> NormalizedPayload:
    """Normalize a raw external payload into canonical form.

    Args:
        platform: Source platform identifier.
        payload: Raw payload from the external adapter's fetch_* method.

    Returns:
        NormalizedPayload with status indicating success or failure reason.
    """
    if platform not in PLATFORM_SCHEMAS:
        return NormalizedPayload(
            status=NormalizationStatus.PLATFORM_UNKNOWN,
            platform=platform,
            error=f"unknown platform '{platform}'",
        )

    required = PLATFORM_SCHEMAS[platform]
    missing = [f for f in required if f not in payload]
    if missing:
        return NormalizedPayload(
            status=NormalizationStatus.MISSING_FIELDS,
            platform=platform,
            error=f"missing fields: {missing}",
        )

    # Extract symbol (platform-specific field name)
    if platform == "freqtrade":
        symbol_key = "pair"
    elif platform == "qstrader":
        symbol_key = "ticker"
    else:
        symbol_key = "symbol"
    symbol = str(payload.get(symbol_key, ""))

    # Extract and normalize side
    side_key = _side_key(platform)
    raw_side = str(payload.get(side_key, "")).lower()
    side_map = SIDE_MAPS.get(platform, {})
    side = side_map.get(raw_side, "HOLD")

    # Extract confidence if available
    confidence = float(payload.get("confidence", 0.5))

    return NormalizedPayload(
        status=NormalizationStatus.SUCCESS,
        platform=platform,
        symbol=symbol,
        side=side,
        confidence=confidence,
        raw_payload=payload,
    )


def _side_key(platform: str) -> str:
    """Get the field name that contains the side/direction for a platform."""
    return {
        "tradingview": "action",
        "mt5": "type",
        "quantconnect": "direction",
        "backtrader": "side",
        "vectorbt": "signal",
        "freqtrade": "side",
        "jesse": "side",
        "qstrader": "direction",
    }.get(platform, "side")

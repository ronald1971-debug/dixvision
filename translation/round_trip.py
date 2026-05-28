"""translation.round_trip — Deterministic Round-Trip Validation.

Verifies that every intent can be serialised to a dict and deserialised back
to an identical typed intent, guaranteeing the translation layer introduces
no information loss or mutation.

Manifest §5 (Phase 5) requires round-trip validation for all intent types.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from translation.intent_models import (
    HazardIntent,
    HazardIntentType,
    MarketIntent,
    MarketIntentType,
    SystemIntent,
    SystemIntentType,
)
from translation.translator import get_translator


def _market_from_dict(d: dict[str, Any]) -> MarketIntent:
    return MarketIntent(
        intent_type=MarketIntentType(d["intent_type"]),
        asset=d["asset"],
        side=d["side"],
        size_usd=float(d.get("size_usd", 0.0)),
        price=d.get("price"),
        strategy=d.get("strategy", ""),
    )


def _system_from_dict(d: dict[str, Any]) -> SystemIntent:
    return SystemIntent(
        intent_type=SystemIntentType(d["intent_type"]),
        target=d.get("target", ""),
        payload=d.get("payload", {}),
    )


def _hazard_from_dict(d: dict[str, Any]) -> HazardIntent:
    return HazardIntent(
        intent_type=HazardIntentType(d["intent_type"]),
        severity=d.get("severity", "MEDIUM"),
        details=d.get("details", {}),
    )


def round_trip_market(intent: MarketIntent) -> tuple[bool, str]:
    """Serialise → deserialise a MarketIntent and compare."""
    d = asdict(intent)
    reconstructed = _market_from_dict(d)
    if reconstructed == intent:
        return True, "MarketIntent:round_trip_ok"
    return False, f"MarketIntent:mismatch orig={intent} reconstructed={reconstructed}"


def round_trip_system(intent: SystemIntent) -> tuple[bool, str]:
    """Serialise → deserialise a SystemIntent and compare."""
    d = asdict(intent)
    reconstructed = _system_from_dict(d)
    if reconstructed == intent:
        return True, "SystemIntent:round_trip_ok"
    return False, f"SystemIntent:mismatch orig={intent} reconstructed={reconstructed}"


def round_trip_hazard(intent: HazardIntent) -> tuple[bool, str]:
    """Serialise → deserialise a HazardIntent and compare."""
    d = asdict(intent)
    reconstructed = _hazard_from_dict(d)
    if reconstructed == intent:
        return True, "HazardIntent:round_trip_ok"
    return False, f"HazardIntent:mismatch orig={intent} reconstructed={reconstructed}"


def validate_translator_round_trip() -> list[tuple[bool, str]]:
    """Run round-trip validation on a canonical set of payloads.

    Ensures the Translator produces intents that survive ser/deser.
    """
    translator = get_translator()
    results: list[tuple[bool, str]] = []

    market_payloads = [
        {
            "action": "BUY",
            "asset": "BTCUSDT",
            "side": "LONG",
            "size_usd": 1000.0,
            "price": 65000.0,
            "strategy": "regime_adaptive",
        },
        {"action": "SELL", "asset": "ETHUSDT", "side": "SHORT", "size_usd": 500.0},
        {"action": "HOLD", "asset": "SOLUSDT", "side": "NONE"},
    ]
    for p in market_payloads:
        intent = translator.translate_market(p)
        results.append(round_trip_market(intent))

    system_payloads = [
        {"action": "RESTART_SERVICE", "target": "dyon"},
        {"action": "HEALTH_CHECK"},
    ]
    for p in system_payloads:
        intent = translator.translate_system(p)
        results.append(round_trip_system(intent))

    hazard_intents = [
        HazardIntent(HazardIntentType.EXCHANGE_TIMEOUT, "HIGH", {"exchange": "binance"}),
        HazardIntent(HazardIntentType.FEED_SILENCE, "CRITICAL"),
    ]
    for h in hazard_intents:
        results.append(round_trip_hazard(h))

    return results

"""CORE-15 — translate an ExecutionIntent into a PatchProposal shape.

This module is a pure translation layer: it converts a governance-
approved execution intent into the canonical patch-proposal payload
consumed by the evolution pipeline. It never constructs PatchProposal
directly (B28) — it produces the *payload dict* that the caller wraps
into the appropriate value object.

INV-15: Pure function of inputs — no clocks, no I/O.
B1:     No imports from engine tiers beyond core.contracts.
B28:    Never constructs PatchProposal(...) directly.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

__all__ = ["intent_to_patch_payload", "IntentTranslationError"]


class IntentTranslationError(ValueError):
    """Raised when an intent cannot be translated into a patch payload."""


def intent_to_patch_payload(
    *,
    intent_id: str,
    strategy_id: str,
    parameter: str,
    old_value: Any,
    new_value: Any,
    reason: str,
    ts_ns: int,
    source: str = "translation_layer",
    meta: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return a canonical patch-proposal payload dict.

    The returned dict mirrors the ``UPDATE_PROPOSED`` payload shape
    expected by ``GovernanceEngine._handle_update_proposed``.

    Args:
        intent_id:   Stable identifier of the originating ExecutionIntent.
        strategy_id: Target strategy to patch.
        parameter:   Parameter name to update.
        old_value:   Current parameter value (must be JSON-serialisable).
        new_value:   Proposed parameter value (must be JSON-serialisable).
        reason:      Human-readable rationale.
        ts_ns:       Monotonic timestamp of the originating intent.
        source:      Producer label written to the audit ledger.
        meta:        Optional free-form metadata.

    Returns:
        A ``dict[str, Any]`` ready to be set as the ``payload`` of a
        ``SystemEvent(sub_kind=UPDATE_PROPOSED, ...)``.
    """
    if not intent_id:
        raise IntentTranslationError("intent_id must be non-empty")
    if not strategy_id:
        raise IntentTranslationError("strategy_id must be non-empty")
    if not parameter:
        raise IntentTranslationError("parameter must be non-empty")
    if not reason:
        raise IntentTranslationError("reason must be non-empty")

    payload: dict[str, Any] = {
        "intent_id": intent_id,
        "strategy_id": strategy_id,
        "parameter": parameter,
        "old_value": old_value,
        "new_value": new_value,
        "reason": reason,
        "ts_ns": ts_ns,
        "source": source,
    }
    if meta:
        payload["meta"] = dict(meta)

    # Content hash for INV-15 replay verification.
    canonical = json.dumps(
        {k: payload[k] for k in sorted(payload) if k != "meta"},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    payload["content_hash"] = hashlib.blake2b(
        canonical.encode("utf-8"), digest_size=16
    ).hexdigest()

    return payload

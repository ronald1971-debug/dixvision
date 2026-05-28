"""Cockpit widget — governance panel.

Reads pending patch proposals and trust scores from the live governance engine.
No constructor injection required.
"""

from __future__ import annotations

from typing import Any

__all__ = ["governance_panel_payload"]


def governance_panel_payload() -> dict[str, Any]:
    try:
        from ui.server import STATE  # noqa: PLC0415
        gov = STATE.governance

        # Pending proposals from the governance ledger
        try:
            pending_raw = gov.pending_proposals() if hasattr(gov, "pending_proposals") else []
        except Exception:  # noqa: BLE001
            pending_raw = []

        proposals = [
            {
                "intent_id": getattr(p, "intent_id", str(i)),
                "strategy_id": getattr(p, "strategy_id", ""),
                "parameter": getattr(p, "parameter", ""),
                "old_value": getattr(p, "old_value", None),
                "new_value": getattr(p, "new_value", None),
                "reason": getattr(p, "reason", ""),
                "stage": getattr(p, "stage", "PROPOSED"),
                "ts_ns": getattr(p, "ts_ns", 0),
            }
            for i, p in enumerate(pending_raw)
        ]

        # Trust scores
        try:
            trust_raw = gov.trust_scores() if hasattr(gov, "trust_scores") else []
        except Exception:  # noqa: BLE001
            trust_raw = []

        trust_scores = [
            {
                "source_id": getattr(t, "source_id", str(i)),
                "score": getattr(t, "score", 0.5),
                "streak": getattr(t, "streak", 0),
                "status": (
                    "TRUSTED" if getattr(t, "score", 0) >= 0.7
                    else "PROBATION" if getattr(t, "score", 0) >= 0.4
                    else "SUSPENDED"
                ),
            }
            for i, t in enumerate(trust_raw)
        ]

        return {
            "pending_proposals": proposals,
            "proposals_awaiting_operator": sum(
                1 for p in proposals if p["stage"] in ("DRY_RUN", "VALIDATED")
            ),
            "trust_scores": trust_scores,
        }
    except Exception as exc:  # noqa: BLE001
        return {"pending_proposals": [], "proposals_awaiting_operator": 0,
                "trust_scores": [], "error": str(exc)}

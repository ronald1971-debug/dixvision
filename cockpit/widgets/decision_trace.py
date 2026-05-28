"""Cockpit widget — decision trace viewer.

Reads the live decision trace from STATE.decisions (DecisionTracePanel).
No constructor injection required.
"""

from __future__ import annotations

from typing import Any

__all__ = ["decision_trace_payload"]


def decision_trace_payload(strategy_id: str | None = None, limit: int = 20) -> dict[str, Any]:
    try:
        from ui.server import STATE  # noqa: PLC0415
        panel = STATE.decisions
        entries = panel.recent(limit=limit)
        if strategy_id:
            entries = [e for e in entries if getattr(e, "strategy_id", None) == strategy_id]
        rows = []
        for e in entries:
            rows.append({
                "ts_ns": getattr(e, "ts_ns", 0),
                "strategy_id": getattr(e, "strategy_id", ""),
                "decision": getattr(e, "decision", ""),
                "confidence": getattr(e, "confidence", 0.0),
                "latency_ns": getattr(e, "latency_ns", 0),
                "override_applied": getattr(e, "override_applied", False),
                "signed": getattr(e, "signed", False),
            })
        return {"entries": rows, "count": len(rows)}
    except Exception as exc:  # noqa: BLE001
        return {"entries": [], "count": 0, "error": str(exc)}

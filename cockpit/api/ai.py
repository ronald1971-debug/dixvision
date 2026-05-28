"""Cockpit API — /ai payload builder.

Wraps cockpit.llm (get_router) for the operator AI-provider surface.
Called by ui/cockpit_routes.py.
"""

from __future__ import annotations

from typing import Any

from cockpit.llm import get_router as get_llm_router

__all__ = ["ai_payload"]


def ai_payload() -> dict[str, Any]:
    rows = get_llm_router().status()
    return {
        "providers": [
            {
                "name": s.name,
                "role": s.role,
                "model": s.model,
                "enabled": s.enabled,
                "has_key": s.has_key,
                "capabilities": s.capabilities,
                "cost_per_1k_tokens_usd": s.cost_per_1k_tokens_usd,
                "local": s.local,
                "total_calls": s.total_calls,
                "total_cost_usd": round(s.total_cost_usd, 6),
                "last_error": s.last_error,
            }
            for s in rows
        ],
    }

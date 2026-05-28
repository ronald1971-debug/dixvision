"""Cockpit API — /charters payload builder.

Wraps core.charter.all_charters() for the cockpit operator surface.
Called by ui/cockpit_routes.py.
"""

from __future__ import annotations

from typing import Any

from core.charter import all_charters

__all__ = ["charters_payload"]


def charters_payload() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for voice, c in all_charters().items():
        out.append({
            "voice": voice.value,
            "domain": c.domain.value,
            "what": c.what,
            "how": list(c.how),
            "why": list(c.why),
            "not_do": list(c.not_do),
            "accountability": list(c.accountability),
            "tools": list(c.tools),
            "peers_readable": c.peers_readable,
        })
    return out

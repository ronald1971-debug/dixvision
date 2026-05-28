"""Cockpit API — /scout payload builders."""

from __future__ import annotations

from typing import Any

from system_monitor import weekly_scout as _scout

__all__ = ["scout_payload", "run_scout"]


def scout_payload() -> dict[str, Any]:
    tick = _scout.last_tick()  # ScoutTick | None
    if tick is None:
        return {
            "last_run_utc": None,
            "finished_utc": None,
            "candidates_found": 0,
            "errors": [],
            "running": False,
        }
    return {
        "last_run_utc": tick.started_utc,
        "finished_utc": tick.finished_utc,
        "candidates_found": len(tick.candidates),
        "errors": list(tick.errors),
        "running": tick.finished_utc == "",
    }


def run_scout() -> dict[str, Any]:
    tick = _scout.run_once()  # ScoutTick
    return {
        "triggered": True,
        "started_utc": tick.started_utc,
        "finished_utc": tick.finished_utc,
        "candidates_found": len(tick.candidates),
        "errors": list(tick.errors),
    }

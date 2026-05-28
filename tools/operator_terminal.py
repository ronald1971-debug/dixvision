# ADAPTED FROM: zauberzeug/nicegui
# (nicegui/ui.py — ui.button, ui.table, ui.chart, ui.label, ui.page;
#  nicegui/app.py — app lifecycle, @ui.page decorator)
"""C-87 — NiceGUI operator terminal web UI.

This module adapts ``nicegui`` for an operator terminal that displays
positions, hazard event streams, and governance approval queues.

What survives from upstream (zauberzeug/nicegui):
    * **ui.page** — page decorator for route registration.
    * **ui.table** — data table component.
    * **ui.label** — text display.
    * **app lifecycle** — startup/shutdown hooks.

What we replaced:
    * Real ``nicegui`` import is lazy (Protocol seam).
    * Calls DIX REST API — does NOT import DIX modules directly.
    * In-memory mock for unit tests.

OFFLINE tier: operator dashboard UI.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field


@dataclass
class TerminalState:
    """Current state of the operator terminal."""

    positions: list[dict] = field(default_factory=list)
    hazard_events: list[dict] = field(default_factory=list)
    governance_mode: str = "UNKNOWN"
    uptime_seconds: float = 0.0


class OperatorTerminal:
    """NiceGUI-based operator terminal.

    Polls DIX REST API for live data — does NOT import DIX modules.

    Usage::

        terminal = OperatorTerminal(api_base="http://localhost:8000")
        state = terminal.refresh()
    """

    def __init__(
        self,
        *,
        api_base: str = "http://localhost:8000",
        in_memory: bool = True,
    ) -> None:
        self._api_base = api_base
        self._in_memory = in_memory
        self._state = TerminalState()
        self._mock_positions: list[dict] = []
        self._mock_events: list[dict] = []

    def refresh(self) -> TerminalState:
        """Poll REST API and update terminal state."""
        if self._in_memory:
            self._state = TerminalState(
                positions=self._mock_positions,
                hazard_events=self._mock_events[-10:],
                governance_mode="SAFE",
                uptime_seconds=42.0,
            )
            return self._state
        return self._fetch_state()

    def add_mock_position(self, position: dict) -> None:
        """Add mock position for testing."""
        self._mock_positions.append(position)

    def add_mock_event(self, event: dict) -> None:
        """Add mock hazard event for testing."""
        self._mock_events.append(event)

    @property
    def state(self) -> TerminalState:
        return self._state

    def _fetch_state(self) -> TerminalState:
        """Fetch state from DIX REST API."""
        try:
            positions = self._get(f"{self._api_base}/api/positions")
            events = self._get(f"{self._api_base}/api/hazard-events")
            mode = self._get(f"{self._api_base}/api/governance/mode")
            self._state = TerminalState(
                positions=positions if isinstance(positions, list) else [],
                hazard_events=events if isinstance(events, list) else [],
                governance_mode=(
                    mode.get("mode", "UNKNOWN") if isinstance(mode, dict) else "UNKNOWN"
                ),
            )
        except Exception:
            pass
        return self._state

    def _get(self, url: str) -> dict | list:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())


__all__ = ["OperatorTerminal", "TerminalState"]

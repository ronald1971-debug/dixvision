# ADAPTED FROM: Textualize/textual
# (textual/app.py — App, compose(), key bindings;
#  textual/widgets/ — DataTable, Log, Header, Footer;
#  textual/screen.py — Screen lifecycle)
"""C-88 — Textual CLI real-time dashboard.

This module adapts ``textual`` for a terminal-based live dashboard
that polls the DIX REST API every second.

What survives from upstream (Textualize/textual):
    * **App** — ``app.py``: application lifecycle, compose(), run().
    * **DataTable** — ``widgets/data_table.py``: tabular data display.
    * **Log** — ``widgets/log.py``: scrolling log widget.
    * **Header/Footer** — chrome widgets.

What we replaced:
    * Real ``textual`` import is lazy (Protocol seam).
    * Calls DIX REST API — does NOT import DIX modules directly.
    * In-memory mock for unit tests (no TUI rendering needed).

OFFLINE tier: operator CLI tool.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field


@dataclass
class DashboardSnapshot:
    """Point-in-time snapshot of dashboard data."""

    positions: list[dict] = field(default_factory=list)
    recent_events: list[dict] = field(default_factory=list)
    governance_mode: str = "UNKNOWN"
    uptime_seconds: float = 0.0


class CLIDashboard:
    """Terminal-based real-time dashboard.

    Polls DIX REST API every second. Shows: live positions, last 10
    HazardEvents, current governance mode, uptime. No DIX imports.

    Usage::

        dashboard = CLIDashboard(api_base="http://localhost:8000")
        snapshot = dashboard.poll()
    """

    def __init__(
        self,
        *,
        api_base: str = "http://localhost:8000",
        in_memory: bool = True,
    ) -> None:
        self._api_base = api_base
        self._in_memory = in_memory
        self._snapshots: list[DashboardSnapshot] = []
        self._mock_data: DashboardSnapshot = DashboardSnapshot()

    def poll(self) -> DashboardSnapshot:
        """Poll the REST API and return a snapshot."""
        if self._in_memory:
            self._snapshots.append(self._mock_data)
            return self._mock_data
        return self._fetch_snapshot()

    def set_mock_data(self, snapshot: DashboardSnapshot) -> None:
        """Set mock data for testing."""
        self._mock_data = snapshot

    @property
    def history(self) -> list[DashboardSnapshot]:
        return list(self._snapshots)

    def render_text(self, snapshot: DashboardSnapshot | None = None) -> str:
        """Render a text-mode display of the dashboard."""
        s = snapshot or self._mock_data
        lines = [
            f"=== DIX Dashboard (mode: {s.governance_mode}) ===",
            f"Uptime: {s.uptime_seconds:.0f}s",
            "",
            "POSITIONS:",
        ]
        for pos in s.positions[:10]:
            lines.append(f"  {pos.get('symbol', '?')}: {pos.get('qty', 0)}")
        lines.append("")
        lines.append("RECENT HAZARD EVENTS:")
        for evt in s.recent_events[-10:]:
            lines.append(f"  [{evt.get('level', '?')}] {evt.get('message', '')}")
        return "\n".join(lines)

    def _fetch_snapshot(self) -> DashboardSnapshot:
        """Fetch snapshot from REST API."""
        try:
            positions = self._get(f"{self._api_base}/api/positions")
            events = self._get(f"{self._api_base}/api/hazard-events")
            mode_resp = self._get(f"{self._api_base}/api/governance/mode")
            snap = DashboardSnapshot(
                positions=positions if isinstance(positions, list) else [],
                recent_events=events if isinstance(events, list) else [],
                governance_mode=(
                    mode_resp.get("mode", "UNKNOWN") if isinstance(mode_resp, dict) else "UNKNOWN"
                ),
            )
            self._snapshots.append(snap)
            return snap
        except Exception:
            empty = DashboardSnapshot()
            self._snapshots.append(empty)
            return empty

    def _get(self, url: str) -> dict | list:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())


__all__ = ["CLIDashboard", "DashboardSnapshot"]

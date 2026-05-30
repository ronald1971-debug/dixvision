"""Operator IDE (BUILD-DIRECTIVE — Tier 4.2).

Extends the cockpit with IDE-like operator capabilities:
- Strategy editor (view/edit atom parameters)
- Live signal inspector (real-time signal stream)
- Governance log viewer (decision audit trail)
- Performance dashboard (PnL, Sharpe, drawdown curves)
- Regime monitor (current classification + history)
- System health panel (all engines + sensors)
- Command palette (operator shortcuts)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class IDEPanel(StrEnum):
    """Available IDE panels."""

    STRATEGY_EDITOR = "strategy_editor"
    SIGNAL_INSPECTOR = "signal_inspector"
    GOVERNANCE_LOG = "governance_log"
    PERFORMANCE = "performance"
    REGIME_MONITOR = "regime_monitor"
    SYSTEM_HEALTH = "system_health"
    COMMAND_PALETTE = "command_palette"
    ARCHETYPE_EXPLORER = "archetype_explorer"
    ATOM_BROWSER = "atom_browser"
    REPLAY_VIEWER = "replay_viewer"


@dataclass(frozen=True, slots=True)
class IDELayout:
    """Layout configuration for the operator IDE."""

    panels: tuple[IDEPanel, ...] = (
        IDEPanel.PERFORMANCE,
        IDEPanel.SIGNAL_INSPECTOR,
        IDEPanel.REGIME_MONITOR,
        IDEPanel.SYSTEM_HEALTH,
    )
    density: str = "comfortable"  # "compact" | "comfortable" | "spacious"
    theme: str = "dark"
    columns: int = 2


@dataclass(frozen=True, slots=True)
class CommandEntry:
    """A command palette entry."""

    id: str
    label: str
    shortcut: str
    category: str
    action: str  # callable name


# Default command palette commands
DEFAULT_COMMANDS: tuple[CommandEntry, ...] = (
    CommandEntry("cmd_pause", "Pause All Trading", "Ctrl+Shift+P", "execution", "pause_trading"),
    CommandEntry("cmd_resume", "Resume Trading", "Ctrl+Shift+R", "execution", "resume_trading"),
    CommandEntry("cmd_regime", "Show Current Regime", "Ctrl+G", "intel", "show_regime"),
    CommandEntry("cmd_signals", "Toggle Signal Feed", "Ctrl+S", "intel", "toggle_signals"),
    CommandEntry("cmd_perf", "Performance Summary", "Ctrl+D", "analytics", "show_performance"),
    CommandEntry("cmd_health", "System Health Check", "Ctrl+H", "system", "health_check"),
    CommandEntry("cmd_replay", "Start Replay", "Ctrl+Shift+L", "simulation", "start_replay"),
    CommandEntry("cmd_atoms", "Browse Atoms", "Ctrl+A", "strategy", "browse_atoms"),
    CommandEntry("cmd_archetypes", "Archetype Explorer", "Ctrl+T", "strategy", "show_archetypes"),
    CommandEntry("cmd_kill", "Kill Switch", "Ctrl+Shift+K", "governance", "kill_switch"),
)


@dataclass(slots=True)
class SystemHealthStatus:
    """Health status for all system components."""

    engines: dict[str, str] = field(default_factory=dict)
    sensors: dict[str, str] = field(default_factory=dict)
    feeds: dict[str, str] = field(default_factory=dict)
    plugins: dict[str, str] = field(default_factory=dict)
    databases: dict[str, str] = field(default_factory=dict)


class OperatorIDE:
    """Operator IDE controller.

    Manages IDE state, panel layout, and command dispatch.
    Provides the operator with a unified view of all system state.
    """

    def __init__(self, *, layout: IDELayout | None = None) -> None:
        self._layout = layout or IDELayout()
        self._commands = {c.id: c for c in DEFAULT_COMMANDS}
        self._signal_buffer: list[dict[str, Any]] = []
        self._signal_buffer_max = 500

    @property
    def layout(self) -> IDELayout:
        """Current IDE layout."""
        return self._layout

    @property
    def available_commands(self) -> list[CommandEntry]:
        """All available commands."""
        return list(self._commands.values())

    def search_commands(self, query: str) -> list[CommandEntry]:
        """Search command palette."""
        q = query.lower()
        return [
            c for c in self._commands.values() if q in c.label.lower() or q in c.category.lower()
        ]

    def set_layout(self, layout: IDELayout) -> None:
        """Update IDE layout."""
        self._layout = layout

    def ingest_signal(self, signal: dict[str, Any]) -> None:
        """Add a signal to the inspector buffer."""
        self._signal_buffer.append(signal)
        if len(self._signal_buffer) > self._signal_buffer_max:
            self._signal_buffer = self._signal_buffer[-self._signal_buffer_max :]

    def get_recent_signals(self, *, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent signals from the buffer."""
        return self._signal_buffer[-limit:]

    def get_system_health(self) -> SystemHealthStatus:
        """Get current system health by querying the kernel's service registry.

        Maps ServiceHealth entries from the kernel snapshot into operator-facing
        buckets. Falls back to "unknown" for any engine that is unreachable or
        has not registered with the kernel yet — never fabricates "healthy".
        """
        engines: dict[str, str] = {}
        sensors: dict[str, str] = {}
        feeds: dict[str, str] = {}
        databases: dict[str, str] = {}

        _ENGINE_NAMES = {"intelligence", "execution", "governance", "learning", "evolution", "system"}
        _SENSOR_NAMES = {"market_data", "sentiment", "onchain", "sensory"}
        _FEED_NAMES   = {"binance_ws", "orderflow", "websocket", "feed"}
        _DB_NAMES     = {"ledger", "vector_store", "sqlite", "database", "db"}

        try:
            from core.kernel import get_kernel
            snap = get_kernel().snapshot  # property, no ()
            for svc in snap.services:
                name  = svc.name.lower()
                label = "healthy" if svc.healthy else f"degraded: {svc.detail}" if svc.detail else "degraded"
                if any(n in name for n in _ENGINE_NAMES):
                    engines[svc.name] = label
                elif any(n in name for n in _SENSOR_NAMES):
                    sensors[svc.name] = label
                elif any(n in name for n in _FEED_NAMES):
                    feeds[svc.name] = label
                elif any(n in name for n in _DB_NAMES):
                    databases[svc.name] = label
                else:
                    engines[svc.name] = label
        except Exception:
            pass

        # Fill known slots that weren't reported with explicit "unknown"
        # so the dashboard shows gaps rather than fabricated health.
        for slot in ("intelligence", "execution", "governance", "learning", "evolution"):
            engines.setdefault(slot, "unknown")
        for slot in ("market_data", "sentiment", "onchain"):
            sensors.setdefault(slot, "unknown")
        for slot in ("binance_ws", "orderflow"):
            feeds.setdefault(slot, "unknown")
        for slot in ("ledger", "vector_store"):
            databases.setdefault(slot, "unknown")

        return SystemHealthStatus(
            engines=engines,
            sensors=sensors,
            feeds=feeds,
            plugins={},
            databases=databases,
        )

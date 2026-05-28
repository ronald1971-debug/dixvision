"""runtime.authority_adapter — Bridge server _State to RuntimeAuthorityStore.

The RuntimeAuthorityStore is the single source of truth for the runtime
kernel. This adapter wraps the existing ``ui.server._State`` object so
the kernel, reconciler, and enforcer can read/write through a unified
interface without requiring _State to be restructured.

INV-15: All reads go through this adapter — deterministic replay can
intercept and supply replayed values.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from system import time_source


class SystemMode(StrEnum):
    """Canonical system modes (mirrors governance_engine.mode.SystemMode)."""

    LOCKED = "LOCKED"
    SAFE = "SAFE"
    PAPER = "PAPER"
    CANARY = "CANARY"
    LIVE = "LIVE"
    AUTO = "AUTO"
    DEGRADED = "DEGRADED"
    EMERGENCY_HALT = "EMERGENCY_HALT"


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    """Point-in-time snapshot of the runtime state.

    This is the single authoritative view that all subsystems should read.
    Never construct this manually — only the authority adapter or kernel
    may produce it.
    """

    tick: int
    ts_ns: int
    mode: SystemMode
    kill_switch_active: bool
    health_score: float
    active_intents: int
    pending_fills: int
    drawdown_pct: float
    max_drawdown_floor: float = 4.0
    last_reconcile_tick: int = 0
    last_readiness_level: str = "UNKNOWN"


class ServerStateAuthorityAdapter:
    """Adapter providing RuntimeAuthorityStore interface over _State.

    Thread-safe. All mutations go through the adapter's lock to prevent
    race conditions between the kernel tick loop and HTTP request handlers.
    """

    __slots__ = ("_state", "_lock", "_tick", "_snapshots", "_mode_override")

    def __init__(self, state: Any) -> None:
        self._state = state
        self._lock = threading.Lock()
        self._tick: int = 0
        self._snapshots: list[RuntimeSnapshot] = []
        self._mode_override: SystemMode | None = None

    @property
    def current_tick(self) -> int:
        return self._tick

    def advance_tick(self) -> int:
        """Advance logical tick. Only the kernel may call this."""
        with self._lock:
            self._tick += 1
            return self._tick

    def snapshot(self) -> RuntimeSnapshot:
        """Produce a point-in-time RuntimeSnapshot.

        This is the ONLY way subsystems should read system state.
        """
        with self._lock:
            mode = self._resolve_mode()
            kill_active = self._resolve_kill_switch()
            health = self._resolve_health()
            intents = self._resolve_active_intents()
            fills = self._resolve_pending_fills()
            drawdown = self._resolve_drawdown()

            snap = RuntimeSnapshot(
                tick=self._tick,
                ts_ns=time_source.wall_ns(),
                mode=mode,
                kill_switch_active=kill_active,
                health_score=health,
                active_intents=intents,
                pending_fills=fills,
                drawdown_pct=drawdown,
            )
            self._snapshots.append(snap)
            # Keep last 1000 snapshots for replay
            if len(self._snapshots) > 1000:
                self._snapshots = self._snapshots[-500:]
            return snap

    def _resolve_mode(self) -> SystemMode:
        """Read current system mode from governance state."""
        if self._mode_override:
            return self._mode_override
        try:
            if hasattr(self._state, "governance"):
                gov = self._state.governance
                if hasattr(gov, "mode"):
                    mode_val = gov.mode
                    if hasattr(mode_val, "value"):
                        return SystemMode(mode_val.value)
                    return SystemMode(str(mode_val))
        except (ValueError, KeyError):
            pass
        return SystemMode("PAPER")

    def _resolve_kill_switch(self) -> bool:
        """Check if kill switch is engaged."""
        try:
            if hasattr(self._state, "governance"):
                gov = self._state.governance
                if hasattr(gov, "kill_switch_active"):
                    return bool(gov.kill_switch_active)
                if hasattr(gov, "is_killed"):
                    return bool(gov.is_killed)
        except Exception:
            pass
        return False

    def _resolve_health(self) -> float:
        """Compute aggregate health score [0.0, 1.0]."""
        scores: list[float] = []
        try:
            if hasattr(self._state, "intelligence"):
                eng = self._state.intelligence
                if hasattr(eng, "health_score"):
                    scores.append(float(eng.health_score))
            if hasattr(self._state, "execution"):
                eng = self._state.execution
                if hasattr(eng, "health_score"):
                    scores.append(float(eng.health_score))
            if hasattr(self._state, "governance"):
                eng = self._state.governance
                if hasattr(eng, "health_score"):
                    scores.append(float(eng.health_score))
        except Exception:
            pass
        return sum(scores) / len(scores) if scores else 1.0

    def _resolve_active_intents(self) -> int:
        """Count active execution intents."""
        try:
            if hasattr(self._state, "execution"):
                eng = self._state.execution
                if hasattr(eng, "active_intent_count"):
                    return int(eng.active_intent_count)
                if hasattr(eng, "pending_orders"):
                    return len(eng.pending_orders)
        except Exception:
            pass
        return 0

    def _resolve_pending_fills(self) -> int:
        """Count pending fill confirmations."""
        try:
            if hasattr(self._state, "execution"):
                eng = self._state.execution
                if hasattr(eng, "pending_fill_count"):
                    return int(eng.pending_fill_count)
        except Exception:
            pass
        return 0

    def _resolve_drawdown(self) -> float:
        """Read current portfolio drawdown percentage."""
        try:
            if hasattr(self._state, "execution"):
                eng = self._state.execution
                if hasattr(eng, "current_drawdown_pct"):
                    return float(eng.current_drawdown_pct)
                if hasattr(eng, "drawdown"):
                    return float(eng.drawdown)
        except Exception:
            pass
        return 0.0

    def set_mode(self, mode: SystemMode) -> None:
        """Override system mode (governance propagation)."""
        with self._lock:
            self._mode_override = mode

    def get_history(self, n: int = 100) -> list[RuntimeSnapshot]:
        """Return last N snapshots for replay/debugging."""
        with self._lock:
            return list(self._snapshots[-n:])


__all__ = [
    "RuntimeSnapshot",
    "ServerStateAuthorityAdapter",
    "SystemMode",
]

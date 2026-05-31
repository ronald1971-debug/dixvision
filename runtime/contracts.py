"""runtime.contracts — Tier-1 runtime service contracts.

Typed protocols for components wired through :mod:`runtime.tier_wiring`
and registered via :mod:`runtime.service_registry`. Pure definitions —
no engine imports (INV-08).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class RuntimePhase(StrEnum):
    """Lifecycle phase for a runtime component."""

    COLD = "COLD"
    REGISTERED = "REGISTERED"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"


@runtime_checkable
class RuntimeComponent(Protocol):
    """Minimal contract for unified-kernel-managed components."""

    def activate(self) -> None: ...

    def snapshot(self) -> dict[str, Any]: ...


@runtime_checkable
class RuntimeTickable(Protocol):
    """Optional per-tick hook."""

    def tick(self, *, ts_ns: int) -> Any: ...


@runtime_checkable
class RuntimeService(Protocol):
    """Kernel-registered service surface."""

    @property
    def name(self) -> str: ...

    def check_health(self) -> Any: ...


class PluginLifecycleState(StrEnum):
    """Operator-visible plugin lifecycle (registry + runtime)."""

    DISABLED = "DISABLED"
    SHADOW = "SHADOW"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


@dataclass(frozen=True, slots=True)
class TierSlotStatus:
    """Completion status for one build-tier slot."""

    name: str
    complete: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class TierCompletionReport:
    """Outcome of :func:`runtime.tier_wiring.complete_tier_runtime`."""

    tier0: tuple[TierSlotStatus, ...] = ()
    tier1: tuple[TierSlotStatus, ...] = ()
    tier2: tuple[TierSlotStatus, ...] = ()
    services_registered: int = 0
    plugins_loaded: int = 0
    plugins_active: int = 0
    errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def tier0_complete(self) -> bool:
        return all(s.complete for s in self.tier0) if self.tier0 else False

    @property
    def tier1_complete(self) -> bool:
        return all(s.complete for s in self.tier1) if self.tier1 else False

    @property
    def tier2_complete(self) -> bool:
        return all(s.complete for s in self.tier2) if self.tier2 else False


__all__ = [
    "PluginLifecycleState",
    "RuntimeComponent",
    "RuntimePhase",
    "RuntimeService",
    "RuntimeTickable",
    "TierCompletionReport",
    "TierSlotStatus",
]

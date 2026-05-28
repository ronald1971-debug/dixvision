"""enforcement.resource_enforcer — Resource Budget Enforcement (System Spec §Governance).

Monitors compute, memory, network, and I/O budgets per engine per tick.
Triggers kill switch on budget overrun. Emits HazardEvent on soft-limit breach.
Integrates with drift_oracle for progressive degradation before hard-kill.

Budget thresholds are per-tick, per-engine. The kill switch fires on hard
limits; soft limits emit a RESOURCE_PRESSURE hazard that routes through
Dyon's drift evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from system import time_source


class ResourceType(StrEnum):
    """Types of resource budgets enforced."""

    COMPUTE = "compute"
    MEMORY = "memory"
    NETWORK = "network"
    DISK_IO = "disk_io"
    API_CALLS = "api_calls"


class BudgetStatus(StrEnum):
    """Budget enforcement outcome."""

    WITHIN_BUDGET = "within_budget"
    SOFT_LIMIT = "soft_limit"
    HARD_LIMIT = "hard_limit"
    KILL_TRIGGERED = "kill_triggered"


@dataclass(frozen=True, slots=True)
class ResourceBudget:
    """Per-engine resource budget thresholds."""

    engine_id: str
    compute_budget: float = 100.0
    memory_budget_mb: float = 2048.0
    network_budget_calls: int = 1000
    disk_io_budget_mb: float = 500.0
    api_calls_budget: int = 500
    soft_limit_ratio: float = 0.8
    hard_limit_ratio: float = 1.0


@dataclass(frozen=True, slots=True)
class ResourceUsage:
    """Current resource usage snapshot for an engine."""

    engine_id: str
    compute_used: float = 0.0
    memory_used_mb: float = 0.0
    network_calls: int = 0
    disk_io_mb: float = 0.0
    api_calls: int = 0
    ts_ns: int = field(default_factory=time_source.wall_ns)


@dataclass(frozen=True, slots=True)
class EnforcementResult:
    """Result of a resource enforcement check."""

    engine_id: str
    status: BudgetStatus
    violations: tuple[str, ...]
    ts_ns: int = field(default_factory=time_source.wall_ns)


def _check_limit(
    used: float, budget: float, soft_ratio: float, resource_name: str
) -> tuple[BudgetStatus, str]:
    """Check a single resource against its budget."""
    if budget <= 0:
        return BudgetStatus.WITHIN_BUDGET, ""
    ratio = used / budget
    if ratio >= 1.0:
        return BudgetStatus.HARD_LIMIT, f"{resource_name}: {used:.1f}/{budget:.1f} (100%+)"
    if ratio >= soft_ratio:
        return BudgetStatus.SOFT_LIMIT, f"{resource_name}: {used:.1f}/{budget:.1f} ({ratio:.0%})"
    return BudgetStatus.WITHIN_BUDGET, ""


def enforce_resources(state: Any, *, budget: ResourceBudget | None = None) -> EnforcementResult:
    """Enforce resource budgets against current usage.

    If hard limit exceeded on any resource → trigger kill switch.
    If soft limit exceeded → emit HazardEvent via Dyon.
    Otherwise → pass silently.

    Args:
        state: Object with resource usage attributes (or ResourceUsage).
        budget: Optional explicit budget (defaults from state attributes).

    Returns:
        EnforcementResult with violations and status.
    """
    if budget is None:
        engine_id = getattr(state, "engine_id", "unknown")
        budget = ResourceBudget(engine_id=engine_id)

    compute_used = float(getattr(state, "compute_used", 0.0))
    memory_used = float(getattr(state, "memory_used_mb", 0.0))
    network_calls = int(getattr(state, "network_calls", 0))
    disk_io = float(getattr(state, "disk_io_mb", 0.0))
    api_calls = int(getattr(state, "api_calls", 0))

    violations: list[str] = []
    worst_status = BudgetStatus.WITHIN_BUDGET

    checks = [
        (compute_used, budget.compute_budget, "compute"),
        (memory_used, budget.memory_budget_mb, "memory_mb"),
        (float(network_calls), float(budget.network_budget_calls), "network_calls"),
        (disk_io, budget.disk_io_budget_mb, "disk_io_mb"),
        (float(api_calls), float(budget.api_calls_budget), "api_calls"),
    ]

    for used, limit, name in checks:
        status, msg = _check_limit(used, limit, budget.soft_limit_ratio, name)
        if msg:
            violations.append(msg)
        if status.value > worst_status.value:
            worst_status = status

    if worst_status == BudgetStatus.HARD_LIMIT:
        from immutable_core.kill_switch import trigger_kill_switch

        trigger_kill_switch(
            reason=f"resource_budget_exceeded:{';'.join(violations)}",
            source="resource_enforcer",
        )
        worst_status = BudgetStatus.KILL_TRIGGERED

    if worst_status == BudgetStatus.SOFT_LIMIT:
        try:
            from execution.hazard.event_emitter import get_hazard_emitter

            emitter = get_hazard_emitter("resource_enforcer")
            emitter.emit(
                severity="WARNING",
                hazard_type="RESOURCE_PRESSURE",
                details={"violations": violations, "engine_id": budget.engine_id},
            )
        except Exception:
            pass

    return EnforcementResult(
        engine_id=budget.engine_id,
        status=worst_status,
        violations=tuple(violations),
    )


def enforce_all_engines(
    engines: list[Any], budgets: dict[str, ResourceBudget] | None = None
) -> list[EnforcementResult]:
    """Enforce resource budgets across all active engines.

    Args:
        engines: List of engine state objects.
        budgets: Optional per-engine budget overrides.

    Returns:
        List of EnforcementResult, one per engine.
    """
    results = []
    for engine in engines:
        engine_id = getattr(engine, "engine_id", "unknown")
        budget = budgets.get(engine_id) if budgets else None
        results.append(enforce_resources(engine, budget=budget))
    return results


__all__ = [
    "BudgetStatus",
    "EnforcementResult",
    "ResourceBudget",
    "ResourceType",
    "ResourceUsage",
    "enforce_all_engines",
    "enforce_resources",
]

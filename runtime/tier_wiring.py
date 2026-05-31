"""runtime.tier_wiring — Complete Tier 0–2 runtime integration at boot.

Called from :mod:`runtime.unified_kernel` activation and
:mod:`runtime.boot_integration` when server ``STATE`` is available.
"""

from __future__ import annotations

import logging
from typing import Any

from runtime.contracts import TierCompletionReport, TierSlotStatus

_logger = logging.getLogger(__name__)


def _tier0_status() -> tuple[TierSlotStatus, ...]:
    slots: list[TierSlotStatus] = []

    try:
        import governance.kernel  # noqa: F401

        slots.append(TierSlotStatus("governance_subsystem", True, "governance.kernel importable"))
    except Exception as exc:
        slots.append(TierSlotStatus("governance_subsystem", False, str(exc)))

    try:
        from enforcement.kill_switch import trigger_kill_switch  # noqa: F401

        slots.append(TierSlotStatus("kill_switch_framework", True, "enforcement.kill_switch"))
    except Exception as exc:
        slots.append(TierSlotStatus("kill_switch_framework", False, str(exc)))

    try:
        from governance_engine.risk_engine.risk_tracker import get_risk_tracker

        get_risk_tracker()
        slots.append(TierSlotStatus("risk_controls", True, "risk_tracker singleton"))
    except Exception as exc:
        slots.append(TierSlotStatus("risk_controls", False, str(exc)))

    try:
        from system_monitor.engine import get_system_monitor

        get_system_monitor()
        slots.append(TierSlotStatus("system_health_monitoring", True, "system_monitor"))
    except Exception as exc:
        slots.append(TierSlotStatus("system_health_monitoring", False, str(exc)))

    return tuple(slots)


def complete_tier_runtime(
    *,
    kernel: Any | None = None,
    state: Any | None = None,
) -> TierCompletionReport:
    """Finish Tier 1 and Tier 2 wiring; verify Tier 0."""
    errors: list[str] = []
    tier0 = _tier0_status()

    # Tier 1 — runtime contracts
    from runtime.service_registry import register_tier_services, validate_runtime_contracts

    ok, detail = validate_runtime_contracts()
    tier1_contracts = TierSlotStatus("runtime_contracts", ok, detail)
    if not ok:
        errors.append(detail)

    services_registered = 0
    if kernel is not None:
        try:
            services_registered = register_tier_services(kernel)
            tier1_services = TierSlotStatus(
                "service_registration",
                services_registered > 0,
                f"{services_registered} services",
            )
        except Exception as exc:
            tier1_services = TierSlotStatus("service_registration", False, str(exc))
            errors.append(str(exc))
    else:
        tier1_services = TierSlotStatus("service_registration", False, "no kernel")

    plugins_loaded = 0
    plugins_active = 0
    try:
        from governance_engine.plugin_lifecycle.manager import get_plugin_lifecycle_manager

        mgr = get_plugin_lifecycle_manager()
        if state is not None and hasattr(state, "system_kernel"):
            snap = state.system_kernel.snapshot()
            mgr.set_mode(snap.mode.name)
        mgr.load_registry()
        plugins_active = mgr.apply_registry_status()
        psnap = mgr.snapshot()
        plugins_loaded = int(psnap.get("plugin_count", 0))
        tier1_plugins = TierSlotStatus(
            "plugin_lifecycle_management",
            bool(psnap.get("loaded")) and plugins_loaded > 0,
            f"loaded={plugins_loaded} active={plugins_active}",
        )
    except Exception as exc:
        tier1_plugins = TierSlotStatus("plugin_lifecycle_management", False, str(exc))
        errors.append(str(exc))

    tier1 = (tier1_contracts, tier1_services, tier1_plugins)

    # Tier 2
    try:
        from evolution_engine.runtime_wiring import wire_evolution_runtime

        evo = wire_evolution_runtime(state)
        tier2_evo = TierSlotStatus(
            "evolution_engine_wiring",
            evo.orchestrator_wired and evo.governed_pipeline_wired,
            evo.detail,
        )
    except Exception as exc:
        tier2_evo = TierSlotStatus("evolution_engine_wiring", False, str(exc))
        errors.append(str(exc))

    try:
        from learning_engine.runtime_wiring import wire_learning_runtime

        learn = wire_learning_runtime(state)
        tier2_learn = TierSlotStatus(
            "learning_feedback_loops",
            learn.governed_context_wired or learn.closed_loop_wired,
            learn.detail,
        )
    except Exception as exc:
        tier2_learn = TierSlotStatus("learning_feedback_loops", False, str(exc))
        errors.append(str(exc))

    memory_ok = False
    memory_detail = ""
    try:
        from runtime.memory_coordinator import get_memory_coordinator

        mc = get_memory_coordinator()
        mc.activate()
        memory_ok = True
        memory_detail = "memory_coordinator activated"
    except Exception as exc:
        memory_detail = str(exc)
        errors.append(str(exc))

    tier2_mem = TierSlotStatus("memory_synchronization", memory_ok, memory_detail)
    tier2 = (tier2_evo, tier2_learn, tier2_mem)

    report = TierCompletionReport(
        tier0=tier0,
        tier1=tier1,
        tier2=tier2,
        services_registered=services_registered,
        plugins_loaded=plugins_loaded,
        plugins_active=plugins_active,
        errors=tuple(errors),
    )
    _logger.info(
        "tier_wiring: T0=%s T1=%s T2=%s services=%d plugins=%d",
        report.tier0_complete,
        report.tier1_complete,
        report.tier2_complete,
        services_registered,
        plugins_loaded,
    )
    return report


__all__ = ["complete_tier_runtime"]

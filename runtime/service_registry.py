"""runtime.service_registry — Tier-1 service registration for SystemKernel.

Extends :func:`runtime.service_wiring.register_all_services` with
cognitive runtime, evolution, learning, plugin lifecycle, and fabric
components so ``/api/health`` and kernel snapshots see the full stack.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

from runtime.service_wiring import ModuleService, register_all_services

_logger = logging.getLogger(__name__)

_TIER_SERVICE_FACTORIES: tuple[tuple[str, str, str], ...] = (
    ("unified_kernel", "runtime.unified_kernel", "get_unified_cognitive_kernel"),
    ("memory_coordinator", "runtime.memory_coordinator", "get_memory_coordinator"),
    ("cross_bus_router", "runtime.cross_bus_router", "get_cross_bus_router"),
    ("governance_router", "runtime.governance_router", "get_governance_router"),
    ("cognitive_spine", "runtime.cognitive_spine", "get_cognitive_spine"),
    ("event_fabric", "runtime.unified_fabric.unified", "get_unified_event_fabric"),
    ("evolution_orchestrator", "evolution_engine.evolution_orchestrator", "get_evolution_orchestrator"),
    ("plugin_lifecycle", "governance_engine.plugin_lifecycle.manager", "get_plugin_lifecycle_manager"),
    ("market_context_projector", "governance.market_context_projector", "get_market_context_projector"),
)


def register_tier_services(kernel: Any) -> int:
    """Register Tier-1 runtime services with *kernel*.

    Returns total services registered (base + tier extensions).
    """
    count = register_all_services(kernel)

    for name, mod_path, factory_name in _TIER_SERVICE_FACTORIES:
        try:
            mod = importlib.import_module(mod_path)
            fn = getattr(mod, factory_name, None)
            if fn is None:
                continue
            instance = fn()
            if hasattr(instance, "activate"):
                instance.activate()
            kernel.register_service(ModuleService(name, instance))
            count += 1
        except Exception as exc:
            _logger.debug("service_registry: skip %s: %s", name, exc)

    _logger.info("service_registry: %d kernel services registered", count)
    return count


def validate_runtime_contracts() -> tuple[bool, str]:
    """Verify runtime contract modules import cleanly."""
    try:
        import runtime.contracts  # noqa: F401
        import runtime.unified_fabric.contracts  # noqa: F401
        import core.contracts.events  # noqa: F401
        import core.contracts.governance  # noqa: F401
        return True, "runtime contracts OK"
    except Exception as exc:
        return False, str(exc)


__all__ = [
    "register_tier_services",
    "validate_runtime_contracts",
]

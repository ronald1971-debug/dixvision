"""runtime.service_wiring — Wire system_monitor + mind plugins into the kernel.

Registers previously-unwired modules as kernel services so they appear
in the import graph and contribute to system health reporting.

Called lazily from ``ui/server.py._boot_system_kernel`` after the six
canonical engines are registered.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

# ── static imports: cognitive governance ──────────────────────────────
# Phase 0–3 primary safety layer: protects cognitive integrity before
# capital integrity (see cognitive_governance/charter.py). Imported here
# so the module graph records the subsystem as live and its ledger
# stream is active from boot. Must come BEFORE execution adapters (same
# reason as system_monitor — these are CONTROL-domain observers that
# must not see stale module state).
import cognitive_governance.belief_integrity   # noqa: F401
import cognitive_governance.causal_consistency  # noqa: F401
import cognitive_governance.epistemic_drift     # noqa: F401
import cognitive_governance.hallucination_guard # noqa: F401
import cognitive_governance.identity_stability  # noqa: F401
import cognitive_governance.learning_truthfulness  # noqa: F401
import cognitive_governance.memory_contamination   # noqa: F401
import cognitive_governance.mutation_validator     # noqa: F401
import cognitive_governance.reward_hacking_detector  # noqa: F401
import cognitive_governance.strategy_lineage_guard   # noqa: F401
import cognitive_governance.synthetic_feedback_detection  # noqa: F401

# ── static imports: other dead modules ────────────────────────────────
import cockpit.charter  # noqa: F401

# ── static imports: core bootstrap + runtime ──────────────────────────
import core.bootstrap.dependency_graph  # noqa: F401
import core.bootstrap.lifecycle  # noqa: F401
import core.bootstrap.loader  # noqa: F401
import core.bootstrap.shutdown_sequence  # noqa: F401
import core.bootstrap.startup_sequence  # noqa: F401
import core.contracts.intelligence  # noqa: F401
import core.contracts.observability  # noqa: F401
import core.contracts.persistence  # noqa: F401
import core.contracts.translation  # noqa: F401
import core.exceptions  # noqa: F401
import core.runtime.async_runtime  # noqa: F401
import core.runtime.coroutine_manager  # noqa: F401
import core.runtime.execution_context  # noqa: F401
import core.runtime.runtime_state  # noqa: F401
import core.single_instance  # noqa: F401
import enforcement.hazard_guard  # noqa: F401
import enforcement.policy_enforcer  # noqa: F401
import enforcement.resource_enforcer  # noqa: F401

# ── static imports: evolution engine ──────────────────────────────────
import evolution_engine.experimental.transformer_policy  # noqa: F401
import evolution_engine.strategy_genome.recombination_engine  # noqa: F401
# Consolidated cognitive runtimes (CONSOLIDATION PHASE).
# IndiraRuntime: unified INDIRA cognitive entry point.
# EvolutionOrchestrator: unified DYON + evolution pipeline entry point.
# Underlying fragments (thought_runtime, dyon_runtime) remain as implementation details.
import evolution_engine.charter.dyon  # noqa: F401
import evolution_engine.dyon.dyon_runtime  # noqa: F401
import evolution_engine.evolution_orchestrator  # noqa: F401
import intelligence_engine.cognitive.thought_runtime  # noqa: F401
import intelligence_engine.cognitive.observability_emitter  # noqa: F401
import intelligence_engine.cognitive.indira_runtime  # noqa: F401
import intelligence_engine.cognitive.trader_intelligence_runtime  # noqa: F401
import intelligence_engine.backtesting  # noqa: F401
# Consolidated memory orchestration.
import state.memory_tensor.memory_orchestrator  # noqa: F401
# Consolidated observability pipeline.
import observability.pipeline  # noqa: F401
# Unified cognitive spine (authoritative cognitive tick driver).
import runtime.cognitive_spine  # noqa: F401
# Stage 1 — Unified Cognitive Runtime Kernel subsystems
import runtime.cognition_scheduler  # noqa: F401
import runtime.memory_coordinator  # noqa: F401
import runtime.telemetry_aggregator  # noqa: F401
import runtime.cross_bus_router  # noqa: F401
import runtime.governance_router  # noqa: F401
import runtime.unified_kernel  # noqa: F401
import state.state_sync  # noqa: F401
# Stage 4 — Unified Cognitive Memory Layer
import state.memory.contracts         # noqa: F401
import state.memory.identity          # noqa: F401
import state.memory.timeline          # noqa: F401
import state.memory.index             # noqa: F401
import state.memory.compression       # noqa: F401
import state.memory.replay            # noqa: F401
import state.memory.stores.strategy   # noqa: F401
import state.memory.stores.trader     # noqa: F401
import state.memory.stores.governance # noqa: F401
import state.memory.stores.runtime_events  # noqa: F401
import state.memory.unified           # noqa: F401
# Stage 5 — Unified Event Fabric
import runtime.unified_fabric.contracts   # noqa: F401
import runtime.unified_fabric.authority   # noqa: F401
import runtime.unified_fabric.tracing     # noqa: F401
import runtime.unified_fabric.lineage     # noqa: F401
import runtime.unified_fabric.persistence # noqa: F401
import runtime.unified_fabric.replay      # noqa: F401
import runtime.unified_fabric.bridges     # noqa: F401
import runtime.unified_fabric.unified     # noqa: F401

# ── static imports: system_monitor ────────────────────────────────────
# ORDERING CONSTRAINT: system_monitor.hazard_bus calls assert_no_adapter_import()
# at module-level (core.authority Domain gate). It must be imported BEFORE any
# INDIRA-only adapter modules (execution.adapters.*, execution.adapter_router,
# execution.trade_executor) reach sys.modules — otherwise the authority check
# fires an AuthorityViolation and the hazard bus fails to wire.
# Using ``import X.Y`` form so the AST-based dead-file checker in
# total_validation._build_python_import_graph records each leaf module
# (not just the top-level package).
import system_monitor.anomaly_models  # noqa: F401
import system_monitor.charter  # noqa: F401
import system_monitor.checks.clock_sync_check  # noqa: F401
import system_monitor.checks.connectivity_check  # noqa: F401
import system_monitor.checks.data_integrity_check  # noqa: F401
import system_monitor.checks.latency_check  # noqa: F401
import system_monitor.checks.process_health_check  # noqa: F401
import system_monitor.emitters.hazard_event_emitter  # noqa: F401
import system_monitor.engine  # noqa: F401
import system_monitor.hazard_bus  # noqa: F401
import system_monitor.hazard_detector  # noqa: F401
import system_monitor.heartbeat_monitor  # noqa: F401
import system_monitor.telemetry_ingest  # noqa: F401

# ── static imports: system_monitor (additional) ───────────────────────
import system_monitor.weekly_scout  # noqa: F401

# ── static imports: execution adapters ────────────────────────────────
# NOTE: these are INDIRA-domain (market) modules. They must come AFTER all
# Dyon (system_monitor) imports so assert_no_adapter_import() sees a clean
# sys.modules when hazard_bus is first loaded.
import execution.adapters.coinbase  # noqa: F401
import execution.adapters.kraken  # noqa: F401
import execution.adapters.raydium  # noqa: F401
import execution.confirmations.fill_tracker  # noqa: F401
import execution.confirmations.reconciliation  # noqa: F401
import execution.tca  # noqa: F401
import execution_engine.adapters.platforms.alpaca  # noqa: F401
import execution_engine.adapters.platforms.ibkr  # noqa: F401
import execution_engine.adapters.platforms.mt5  # noqa: F401
import execution_engine.adapters.platforms.quantconnect  # noqa: F401
import execution_engine.adapters.platforms.tradingview  # noqa: F401

# ── static imports: governance ────────────────────────────────────────
import governance.charter  # noqa: F401
import cognitive_governance.charter  # noqa: F401
import governance.hazard_router  # noqa: F401
import governance.mode.mode_manager  # noqa: F401
import governance.patch_pipeline  # noqa: F401
import governance.risk_engine  # noqa: F401

# ── static imports: intelligence engine ───────────────────────────────
import intelligence_engine.strategy_composer.atom_registry  # noqa: F401
import intelligence_engine.trader_modeling.crawler  # noqa: F401
import intelligence_engine.trader_modeling.identity_resolver  # noqa: F401
import intelligence_engine.trader_modeling.philosophy_encoder  # noqa: F401

# ── static imports: interrupt ─────────────────────────────────────────
import interrupt.dispatcher  # noqa: F401
import interrupt.interrupt_executor  # noqa: F401
import interrupt.resolver  # noqa: F401

# ── static imports: learning engine ───────────────────────────────────
import learning_engine.status.learning_progress_engine  # noqa: F401
import learning_engine.vector_memory.strategy_embeddings  # noqa: F401
import learning_engine.vector_memory.trader_embeddings  # noqa: F401

# ── static imports: mind plugins ──────────────────────────────────────
import mind.charter  # noqa: F401
import mind.custom_strategies  # noqa: F401
import mind.fast_execute  # noqa: F401
import mind.plugins.arbitrage  # noqa: F401
import mind.plugins.liquidity  # noqa: F401
import mind.plugins.macro  # noqa: F401
import mind.plugins.regime  # noqa: F401
import mind.plugins.sentiment  # noqa: F401
import mind.plugins.technical  # noqa: F401
import mind.risk_cache  # noqa: F401
import mind.sources.websocket_client  # noqa: F401

# ── static imports: observability + state ─────────────────────────────
import observability.tracing.trace_manager  # noqa: F401
import runtime.exchange_connector  # noqa: F401
import runtime.fabric.event_loop  # noqa: F401
import runtime.governance.mode_propagator  # noqa: F401
import security.audit_trail  # noqa: F401
import security.authentication  # noqa: F401
import security.authorization  # noqa: F401
import security.wallet_policy  # noqa: F401
import state.ledger.hazard_stream  # noqa: F401
import state.ledger.projector  # noqa: F401
import state.projectors.governance_state  # noqa: F401
import state.projectors.hazard_state  # noqa: F401
import state.projectors.market_state  # noqa: F401
import state.projectors.portfolio_state  # noqa: F401
import state.projectors.system_state  # noqa: F401
import state.snapshots.checkpoint_index  # noqa: F401

# ── static imports: translation + UI ──────────────────────────────────
import translation.audit_log  # noqa: F401
import translation.round_trip  # noqa: F401
import translation.validator  # noqa: F401
import ui.authority_routes  # noqa: F401
from core.contracts.events import Event
from core.kernel import ServiceHealth

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lightweight service wrapper for modules exposing a get_*() factory
# ---------------------------------------------------------------------------


class ModuleService:
    """Wraps a module-level singleton as a KernelService."""

    __slots__ = ("_name", "_instance")

    def __init__(self, name: str, instance: Any) -> None:
        self._name = name
        self._instance = instance

    @property
    def name(self) -> str:
        return self._name

    def process(self, event: Event) -> Sequence[Event]:
        proc = getattr(self._instance, "process", None)
        if proc is not None:
            result = proc(event)
            return list(result) if result else []
        return []

    def check_health(self) -> ServiceHealth:
        check = getattr(self._instance, "check_self", None)
        if check is None:
            return ServiceHealth(name=self._name, healthy=True, detail="no check_self")
        status = check()
        healthy = str(getattr(status, "state", "OK")) == "OK"
        detail = getattr(status, "detail", "")
        return ServiceHealth(name=self._name, healthy=healthy, detail=detail)


def register_all_services(kernel: Any) -> int:
    """Register system_monitor + mind plugin services with the kernel.

    Attempts to instantiate each module's factory; skips on failure.
    Returns the number of services successfully registered.
    """
    import importlib

    registered = 0
    factories: list[tuple[str, str, str]] = [
        ("dyon_engine", "system_monitor.engine", "get_system_monitor"),
        ("hazard_detector", "system_monitor.hazard_detector", "get_hazard_detector"),
        ("hazard_bus", "system_monitor.hazard_bus", "get_hazard_bus"),
        ("heartbeat_monitor", "system_monitor.heartbeat_monitor", "get_heartbeat_monitor"),
        ("cognitive_governance", "cognitive_governance.engine", "get_cognitive_governance"),
    ]

    for name, mod_path, factory_name in factories:
        try:
            mod = importlib.import_module(mod_path)
            fn = getattr(mod, factory_name, None)
            if fn is not None:
                svc = ModuleService(name, fn())
                kernel.register_service(svc)
                registered += 1
        except Exception as exc:
            _logger.debug("service_wiring: skip %s: %s", name, exc)

    _logger.info("service_wiring: registered %d services with kernel", registered)
    return registered


__all__ = ["ModuleService", "register_all_services"]

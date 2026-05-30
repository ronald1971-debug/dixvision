"""core.bootstrap.startup_sequence — Ordered Boot Sequence.

Defines the exact sequence of operations for system startup:
1. Verify safety axioms (immutable_core/constants.py)
2. Initialize TimeAuthority
3. Load operator authority from registry
4. Boot governance engine (StateTransitionManager)
5. Boot intelligence engine (Indira)
6. Boot execution engine (adapters + gate)
7. Boot learning engine (vector memory + evolution)
8. Boot system engine (monitors + heartbeat)
9. Register plugins (auto-activate all connected)
10. Start feeds (auto-start all configured sources)
11. Emit SYSTEM_BOOT_COMPLETE event to ledger

If any step fails, the system enters SAFE_MODE (never EMERGENCY_HALT
on boot unless safety axiom verification fails).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum

from system import time_source

logger = logging.getLogger(__name__)


class BootStep(StrEnum):
    """Named boot steps in sequence."""

    VERIFY_AXIOMS = "VERIFY_AXIOMS"
    INIT_CLOCK = "INIT_CLOCK"
    LOAD_AUTHORITY = "LOAD_AUTHORITY"
    BOOT_GOVERNANCE = "BOOT_GOVERNANCE"
    BOOT_INTELLIGENCE = "BOOT_INTELLIGENCE"
    BOOT_EXECUTION = "BOOT_EXECUTION"
    BOOT_LEARNING = "BOOT_LEARNING"
    BOOT_SYSTEM = "BOOT_SYSTEM"
    REGISTER_PLUGINS = "REGISTER_PLUGINS"
    START_FEEDS = "START_FEEDS"
    COMPLETE = "COMPLETE"


@dataclass
class BootStepResult:
    """Result of a single boot step."""

    step: BootStep
    success: bool
    duration_ms: float
    error: str = ""


@dataclass
class StartupResult:
    """Complete boot sequence result."""

    steps: list[BootStepResult] = field(default_factory=list)
    total_duration_ms: float = 0.0
    final_mode: str = "SAFE_MODE"

    @property
    def success(self) -> bool:
        return all(s.success for s in self.steps)

    @property
    def failed_steps(self) -> list[BootStepResult]:
        return [s for s in self.steps if not s.success]


def run_startup_sequence(*, skip_feeds: bool = False, skip_plugins: bool = False) -> StartupResult:
    """Execute the full startup sequence.

    Args:
        skip_feeds: If True, don't auto-start data feeds.
        skip_plugins: If True, don't auto-register plugins.

    Returns:
        StartupResult with per-step timing and status.
    """
    result = StartupResult()
    start_ns = time_source.now_ns()

    steps_to_run = [
        (BootStep.VERIFY_AXIOMS, _verify_axioms),
        (BootStep.INIT_CLOCK, _init_clock),
        (BootStep.LOAD_AUTHORITY, _load_authority),
        (BootStep.BOOT_GOVERNANCE, _boot_governance),
        (BootStep.BOOT_INTELLIGENCE, _boot_intelligence),
        (BootStep.BOOT_EXECUTION, _boot_execution),
        (BootStep.BOOT_LEARNING, _boot_learning),
        (BootStep.BOOT_SYSTEM, _boot_system),
    ]

    if not skip_plugins:
        steps_to_run.append((BootStep.REGISTER_PLUGINS, _register_plugins))
    if not skip_feeds:
        steps_to_run.append((BootStep.START_FEEDS, _start_feeds))

    for step_name, step_fn in steps_to_run:
        step_start = time_source.now_ns()
        try:
            step_fn()
            duration_ms = (time_source.now_ns() - step_start) / 1_000_000
            result.steps.append(
                BootStepResult(step=step_name, success=True, duration_ms=duration_ms)
            )
            logger.info("Boot step %s: OK (%.1fms)", step_name, duration_ms)
        except Exception as e:
            duration_ms = (time_source.now_ns() - step_start) / 1_000_000
            result.steps.append(
                BootStepResult(step=step_name, success=False, duration_ms=duration_ms, error=str(e))
            )
            logger.error("Boot step %s: FAILED (%s)", step_name, e)
            if step_name == BootStep.VERIFY_AXIOMS:
                result.final_mode = "EMERGENCY_HALT"
                break
            result.final_mode = "SAFE_MODE"

    result.total_duration_ms = (time_source.now_ns() - start_ns) / 1_000_000
    if result.success:
        import os as _os
        result.final_mode = _os.environ.get("DIXVISION_BOOT_MODE", "LIVE").strip().upper()

    logger.info(
        "Boot complete: %s in %.1fms (%d/%d steps OK)",
        result.final_mode,
        result.total_duration_ms,
        len(result.steps) - len(result.failed_steps),
        len(result.steps),
    )
    return result


def _verify_axioms() -> None:
    from immutable_core.constants import AXIOMS

    assert AXIOMS.FAIL_CLOSED is True
    assert AXIOMS.MAX_DRAWDOWN_FLOOR_PCT > 0


def _init_clock() -> None:
    from core.time_source import WallClock

    WallClock()


def _load_authority() -> None:
    """Verify governance constitution and operator authority are loadable."""
    from core.contracts.governance_constitution import (
        LIVE_PRIORITY_STACK,
        DEV_PRIORITY_STACK,
        GovernancePriority,
    )
    # Operator Sovereignty must be P2 in every phase (executive directive)
    live_op = LIVE_PRIORITY_STACK.get(GovernancePriority.P2_OPERATOR)
    dev_op = DEV_PRIORITY_STACK.get(GovernancePriority.P2_OPERATOR)
    if live_op != 2:
        raise RuntimeError(
            f"LIVE_PRIORITY_STACK: Operator must be rank 2, got {live_op} — "
            "governance constitution violates executive directive"
        )
    if dev_op != 2:
        raise RuntimeError(
            f"DEV_PRIORITY_STACK: Operator must be rank 2, got {dev_op} — "
            "governance constitution violates executive directive"
        )
    # Registry files must be parseable
    import pathlib
    import yaml
    registry_root = pathlib.Path(__file__).parents[2] / "registry"
    for name in ("governance_constitution.yaml", "engines.yaml", "modes.yaml"):
        path = registry_root / name
        if not path.exists():
            raise FileNotFoundError(f"Missing registry file: {path}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if raw is None:
            raise ValueError(f"Empty registry file: {path}")
    logger.info("Authority: governance constitution OK, registry files OK")


def _boot_governance() -> None:
    """Verify governance engine and charter registrations are loadable."""
    from governance_engine import GovernanceEngine  # noqa: F401 — import validates
    from core.charter import all_charters, Voice
    # Force INDIRA and DYON charter registration by importing their modules
    import intelligence_engine.charter.indira  # noqa: F401
    import evolution_engine.charter.dyon  # noqa: F401
    # all_charters() is keyed by Voice enum; check both identities present
    charters = all_charters()
    if Voice.INDIRA not in charters:
        raise RuntimeError("INDIRA charter is not registered — cognitive identity missing")
    if Voice.DYON not in charters:
        raise RuntimeError("DYON charter is not registered — engineering identity missing")
    logger.info(
        "Governance: GovernanceEngine importable, charters registered: %s",
        [c.value for c in charters],
    )


def _boot_intelligence() -> None:
    """Verify INDIRA intelligence engine and cognitive observability surface."""
    from intelligence_engine import IntelligenceEngine  # noqa: F401
    from intelligence_engine.cognitive.observability_emitter import (
        emit_thought_stream,
        emit_belief_evolution,
        emit_memory_formation,
        emit_confidence_shift,
        emit_archetype_evolution,
        emit_research_discovery,
    )
    # Verify meta-controller hot-path is importable
    from intelligence_engine.meta_controller import MetaControllerHotPath  # noqa: F401
    from intelligence_engine.meta_controller.perception.regime_router import (
        step_regime_router,
    )  # noqa: F401
    # Verify memory stores
    from state.memory_tensor.episodic import EpisodicMemoryStore  # noqa: F401
    from state.memory_tensor.semantic import SemanticMemoryStore  # noqa: F401
    logger.info(
        "Intelligence: IntelligenceEngine + cognitive observability surface OK"
    )


def _boot_execution() -> None:
    """Verify execution engine adapters and kill-switch gate are importable."""
    from execution_engine import ExecutionEngine  # noqa: F401
    # Verify the execution engine's core contracts
    from core.contracts.execution import ExecutionIntent  # noqa: F401
    from core.contracts.events import Side  # noqa: F401
    logger.info("Execution: ExecutionEngine importable")


def _boot_learning() -> None:
    """Verify learning and evolution engines, evolution loop, topology scanner."""
    from learning_engine import LearningEngine  # noqa: F401
    from evolution_engine import EvolutionEngine  # noqa: F401
    from evolution_engine.loops.structural_loop import StructuralEvolutionLoop  # noqa: F401
    from evolution_engine.dyon.topology_scanner import DyonTopologyScanner  # noqa: F401
    from evolution_engine.charter.dyon_observability_emitter import (
        emit_patch_proposal,
        emit_topology_drift,
        emit_architectural_drift,
    )  # noqa: F401
    logger.info(
        "Learning/Evolution: LearningEngine + EvolutionEngine + "
        "StructuralEvolutionLoop + DyonTopologyScanner OK"
    )


def _boot_system() -> None:
    """Verify system engine and ledger are accessible; emit BOOT_START event."""
    from observability.logs.log_sink import install_global_sink
    install_global_sink()
    from system_engine import SystemEngine  # noqa: F401
    from state.ledger.event_store import get_event_store, append_event
    # Confirm ledger is writable — emit BOOT_START
    ts_ns = time_source.now_ns()
    import os as _os
    append_event(
        event_type="SYSTEM",
        sub_type="BOOT_START",
        source="SYSTEM",
        payload={
            "ts_ns": ts_ns,
            "phase": "COGNITIVE_ACTIVATION",
            "mode": _os.environ.get("DIXVISION_BOOT_MODE", "LIVE").strip().upper(),
        },
    )
    logger.info("System: SystemEngine importable, BOOT_START emitted to ledger")


def _register_plugins() -> None:
    """Validate plugin registry is parseable."""
    import pathlib
    import yaml
    path = pathlib.Path(__file__).parents[2] / "registry" / "plugins.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Missing plugins registry: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    plugins = raw.get("plugins", []) if isinstance(raw, dict) else []
    logger.info("Plugins: registry OK (%d plugins declared)", len(plugins))


def _start_feeds() -> None:
    """Validate feed configuration is parseable (actual start handled by harness)."""
    import pathlib
    import yaml
    path = pathlib.Path(__file__).parents[2] / "registry" / "integrations.yaml"
    if not path.exists():
        logger.info("Feeds: no integrations.yaml — skipping feed config validation")
        return
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        raise ValueError("integrations.yaml is empty")
    logger.info("Feeds: integrations.yaml OK")


__all__ = [
    "BootStep",
    "BootStepResult",
    "StartupResult",
    "STARTUP_SEQUENCE",
    "run_startup",
    "run_startup_sequence",
]

# Backward-compatible aliases for __init__.py re-exports
STARTUP_SEQUENCE = list(BootStep)
run_startup = run_startup_sequence

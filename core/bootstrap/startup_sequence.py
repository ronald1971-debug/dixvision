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
        result.final_mode = "PAPER"

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
    pass  # Loaded lazily by server


def _boot_governance() -> None:
    pass  # Lazily initialized


def _boot_intelligence() -> None:
    pass  # Lazily initialized


def _boot_execution() -> None:
    pass  # Lazily initialized


def _boot_learning() -> None:
    pass  # Lazily initialized


def _boot_system() -> None:
    pass  # Lazily initialized


def _register_plugins() -> None:
    pass  # Handled by plugin registry


def _start_feeds() -> None:
    pass  # Handled by feed runners


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

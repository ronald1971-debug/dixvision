"""
core/bootstrap/shutdown_sequence.py
Canonical ordered shutdown steps.
"""

from __future__ import annotations

import logging

_logger = logging.getLogger(__name__)

SHUTDOWN_SEQUENCE: list[tuple[str, str]] = [
    ("mode_halted", "Transition system mode → HALTED"),
    ("dyon_stop", "Stop Dyon system engine"),
    ("guardian_stop", "Stop runtime guardian"),
    ("hazard_bus_drain", "Drain hazard bus"),
    ("ledger_flush", "Flush event store writer"),
    ("audit_shutdown_complete", "Emit SHUTDOWN_COMPLETE audit record"),
]


def run_shutdown() -> dict[str, bool]:
    """Execute the canonical shutdown sequence.

    Returns a dict mapping each step name to True (success) / False (failed).
    Every step is attempted regardless of prior failures so that we drain
    as much state as possible before process exit.
    """
    results: dict[str, bool] = {}

    try:
        from system.state import get_state_manager
        get_state_manager().set_mode("HALTED")
        results["mode_halted"] = True
    except Exception as exc:
        _logger.error("shutdown: mode_halted failed: %s", exc, exc_info=True)
        results["mode_halted"] = False

    try:
        from execution.engine import get_dyon_engine
        get_dyon_engine().stop()
        results["dyon_stop"] = True
    except Exception as exc:
        _logger.error("shutdown: dyon_stop failed: %s", exc, exc_info=True)
        results["dyon_stop"] = False

    try:
        from enforcement.runtime_guardian import get_runtime_guardian
        get_runtime_guardian().stop()
        results["guardian_stop"] = True
    except Exception as exc:
        _logger.error("shutdown: guardian_stop failed: %s", exc, exc_info=True)
        results["guardian_stop"] = False

    try:
        from execution.hazard.async_bus import get_hazard_bus
        get_hazard_bus().stop()
        results["hazard_bus_drain"] = True
    except Exception as exc:
        _logger.error("shutdown: hazard_bus_drain failed: %s", exc, exc_info=True)
        results["hazard_bus_drain"] = False

    try:
        from state.ledger.writer import get_writer
        get_writer().stop()
        results["ledger_flush"] = True
    except Exception as exc:
        _logger.error("shutdown: ledger_flush failed: %s", exc, exc_info=True)
        results["ledger_flush"] = False

    try:
        from state.ledger.event_store import append_event
        append_event("SYSTEM", "SHUTDOWN_COMPLETE", "shutdown_sequence", {"results": results})
        results["audit_shutdown_complete"] = True
    except Exception as exc:
        _logger.error("shutdown: audit_shutdown_complete failed: %s", exc, exc_info=True)
        results["audit_shutdown_complete"] = False

    failed = [k for k, v in results.items() if not v]
    if failed:
        _logger.critical("shutdown: %d steps failed: %s", len(failed), failed)
    else:
        _logger.info("shutdown: all steps completed successfully")

    return results

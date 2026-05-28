"""P4 — governance alignment tests.

Pins the invariants added in the governance-alignment phase:

1. ``RuntimeBootstrap._kernel`` is set when ``_boot()`` runs and
   ``state.system_kernel`` is present.
2. When the kernel transitions mode, the snapshot listener calls
   ``ModePropagator.propagate()`` so both FSMs stay in sync.
3. When ``COGOV_CRITICAL_VIOLATION`` arrives on EventFabric.GOVERNANCE,
   the handler calls ``SystemKernel.transition_mode(SAFE)`` — kernel is
   the canonical writer, not the propagator.
4. ``RuntimeBootstrap.kernel`` property exposes the wired kernel ref.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.contracts.governance import SystemMode
from runtime.boot_integration import RuntimeBootstrap

# _boot() uses lazy local imports, so we patch the *source* modules, not
# "runtime.boot_integration.<name>".
_PATCHES = {
    "event_fabric": "runtime.event_fabric.get_event_fabric",
    "enforcer": "runtime.governance.runtime_enforcer.RuntimeGovernanceEnforcer",
    "reconciler": "runtime.reconciliation.StateReconciler",
    "replay": "runtime.replay_validator.ReplayValidator",
    "readiness": "runtime.operational_readiness.OperationalReadinessValidator",
    "fault": "runtime.fault_handler.FaultHandler",
    "lifecycle": "runtime.execution_lifecycle.get_lifecycle_manager",
    "propagator": "runtime.governance.mode_propagator.ModePropagator",
}


def _make_mock_kernel(initial_mode: SystemMode = SystemMode.PAPER) -> MagicMock:
    kernel = MagicMock()
    snap = MagicMock()
    # Use a real SystemMode so .name works without setting it.
    snap.mode = initial_mode
    kernel.snapshot = snap
    kernel.on_snapshot_change = MagicMock()
    kernel.transition_mode = MagicMock(return_value=True)
    return kernel


def _make_state(kernel: MagicMock) -> MagicMock:
    state = MagicMock()
    state.system_kernel = kernel
    state.authority_store = MagicMock()
    state.authority_store.bind_kernel = MagicMock()
    state.execution = MagicMock()
    state.governance = MagicMock()
    state.intelligence = MagicMock()
    return state


# ---------------------------------------------------------------------------
# kernel property
# ---------------------------------------------------------------------------


def test_kernel_property_none_before_boot() -> None:
    assert RuntimeBootstrap().kernel is None


def test_kernel_property_set_after_boot() -> None:
    """After _boot(), bootstrap.kernel is state.system_kernel."""
    import asyncio

    bootstrap = RuntimeBootstrap()
    kernel = _make_mock_kernel()

    with (
        patch(_PATCHES["event_fabric"]) as _ef,
        patch(_PATCHES["enforcer"]),
        patch(_PATCHES["reconciler"]),
        patch(_PATCHES["replay"]),
        patch(_PATCHES["readiness"]) as _r,
        patch(_PATCHES["fault"]),
        patch(_PATCHES["lifecycle"]),
        patch(_PATCHES["propagator"]),
    ):
        _ef.return_value = MagicMock()
        _r.return_value.assess.return_value = MagicMock(
            level="OPERATIONAL", passed_checks=5, total_checks=5
        )
        asyncio.get_event_loop().run_until_complete(bootstrap._boot(_make_state(kernel)))

    assert bootstrap.kernel is kernel


# ---------------------------------------------------------------------------
# Kernel snapshot listener keeps propagator in sync
# ---------------------------------------------------------------------------


def test_snapshot_listener_propagates_mode_change() -> None:
    """When the kernel mode changes, propagator.propagate() is called."""
    import asyncio

    bootstrap = RuntimeBootstrap()
    kernel = _make_mock_kernel(SystemMode.PAPER)
    captured_listener: list = []
    kernel.on_snapshot_change.side_effect = lambda fn: captured_listener.append(fn)

    mock_propagator = MagicMock()

    with (
        patch(_PATCHES["event_fabric"]) as _ef,
        patch(_PATCHES["enforcer"]),
        patch(_PATCHES["reconciler"]),
        patch(_PATCHES["replay"]),
        patch(_PATCHES["readiness"]) as _r,
        patch(_PATCHES["fault"]),
        patch(_PATCHES["lifecycle"]),
        patch(_PATCHES["propagator"]) as _p,
    ):
        _ef.return_value = MagicMock()
        _r.return_value.assess.return_value = MagicMock(
            level="OPERATIONAL", passed_checks=5, total_checks=5
        )
        _p.return_value = mock_propagator
        asyncio.get_event_loop().run_until_complete(bootstrap._boot(_make_state(kernel)))

    assert len(captured_listener) == 1, "Exactly one snapshot listener should be registered"

    new_snap = MagicMock()
    new_snap.mode.name = "SAFE"
    captured_listener[0](new_snap)

    mock_propagator.propagate.assert_called_once_with("SAFE", triggered_by="kernel_fsm")


def test_snapshot_listener_no_call_on_same_mode() -> None:
    """When mode is unchanged, propagator.propagate() is NOT called."""
    import asyncio

    bootstrap = RuntimeBootstrap()
    kernel = _make_mock_kernel(SystemMode.PAPER)
    captured_listener: list = []
    kernel.on_snapshot_change.side_effect = lambda fn: captured_listener.append(fn)

    mock_propagator = MagicMock()

    with (
        patch(_PATCHES["event_fabric"]) as _ef,
        patch(_PATCHES["enforcer"]),
        patch(_PATCHES["reconciler"]),
        patch(_PATCHES["replay"]),
        patch(_PATCHES["readiness"]) as _r,
        patch(_PATCHES["fault"]),
        patch(_PATCHES["lifecycle"]),
        patch(_PATCHES["propagator"]) as _p,
    ):
        _ef.return_value = MagicMock()
        _r.return_value.assess.return_value = MagicMock(
            level="OPERATIONAL", passed_checks=5, total_checks=5
        )
        _p.return_value = mock_propagator
        asyncio.get_event_loop().run_until_complete(bootstrap._boot(_make_state(kernel)))

    same_snap = MagicMock()
    same_snap.mode.name = "PAPER"  # same as initial
    captured_listener[0](same_snap)

    mock_propagator.propagate.assert_not_called()


# ---------------------------------------------------------------------------
# COGOV_CRITICAL_VIOLATION routes through kernel
# ---------------------------------------------------------------------------


def test_cogov_violation_calls_kernel_transition() -> None:
    """COGOV_CRITICAL_VIOLATION triggers kernel.transition_mode(SAFE)."""
    import asyncio

    bootstrap = RuntimeBootstrap()
    kernel = _make_mock_kernel(SystemMode.PAPER)
    captured_gov_handler: list = []

    def _capture_subscribe(channel, sub_id, callback):
        from runtime.event_fabric import EventChannel
        if channel == EventChannel.GOVERNANCE:
            captured_gov_handler.append(callback)

    mock_fabric = MagicMock()
    mock_fabric.subscribe.side_effect = _capture_subscribe

    with (
        patch(_PATCHES["event_fabric"]) as _ef,
        patch(_PATCHES["enforcer"]),
        patch(_PATCHES["reconciler"]),
        patch(_PATCHES["replay"]),
        patch(_PATCHES["readiness"]) as _r,
        patch(_PATCHES["fault"]),
        patch(_PATCHES["lifecycle"]),
        patch(_PATCHES["propagator"]),
    ):
        _ef.return_value = mock_fabric
        _r.return_value.assess.return_value = MagicMock(
            level="OPERATIONAL", passed_checks=5, total_checks=5
        )
        asyncio.get_event_loop().run_until_complete(bootstrap._boot(_make_state(kernel)))

    assert len(captured_gov_handler) == 1

    mock_event = MagicMock()
    mock_event.event_type = "COGOV_CRITICAL_VIOLATION"
    mock_event.sequence = 1
    captured_gov_handler[0](mock_event)

    kernel.transition_mode.assert_called_once_with(
        SystemMode.SAFE,
        reason="cognitive_governance",
    )

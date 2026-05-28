"""Unified Runtime Authority — kernel-backed shim (Step 10 migration).

MIGRATED: ``RuntimeAuthorityStore`` no longer holds independent state.
All canonical state lives in :class:`core.kernel.SystemKernel`.  The
store class is retained as a **backward-compatible shim** so existing
fabric components (IngestionBus, DecisionPipeline, ExecutionRouter,
FillReconciler, RiskSnapshotter, EnforcementGate) continue to compile
with zero signature changes.

Reads:   ``store.snapshot`` builds a :class:`RuntimeSnapshot` from
         the kernel's :class:`KernelSnapshot` + local operational fields.
Writes:  ``WriterToken.write()`` delegates canonical fields
         (``system_mode``, ``freeze_active``, ``live_execution_blocked``)
         to the kernel and updates local operational fields in-place.
Subscribes: ``store.subscribe()`` still works — callbacks fire on writes.

New code should read from ``SystemKernel.snapshot`` or
``ui.state_projection``, not from this module.

:class:`RuntimeSnapshot` is kept for backward compatibility with
``runtime.governance.deterministic_arbiter`` and test suites.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from threading import RLock
from typing import TYPE_CHECKING, Final

from core.contracts.operator_authority import (
    OperatorAuthority,
)

if TYPE_CHECKING:
    from core.kernel import SystemKernel

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# RuntimeSnapshot — backward-compatible frozen state
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    """Immutable snapshot of system state at one logical tick.

    Canonical fields (mode, freeze, execution_blocked) are sourced from
    SystemKernel.  Operational fields (health_score, positions, exposure)
    are maintained locally until they are migrated to kernel services.
    """

    version: int = 0
    ts_ns: int = 0

    operator_authority: OperatorAuthority = field(default_factory=OperatorAuthority)

    system_mode: str = "PAPER"

    health_score: float = 1.0
    active_hazards: tuple[str, ...] = ()

    live_execution_blocked: bool = True
    open_positions: int = 0
    total_exposure_usd: float = 0.0
    unrealized_pnl_usd: float = 0.0

    last_market_ts_ns: int = 0
    market_connected: bool = False

    governance_mode: str = "ENFORCING"
    freeze_active: bool = False

    learning_active: bool = True
    evolution_active: bool = True
    current_capability_tier: int = 0


# ---------------------------------------------------------------------------
# WriterToken — kernel-delegating write path
# ---------------------------------------------------------------------------


class WriterToken:
    """Opaque token authorizing state writes.

    Writes to canonical fields (system_mode, freeze_active,
    live_execution_blocked) are forwarded to the SystemKernel.
    Operational fields are updated in the local snapshot.
    """

    __slots__ = ("_holder", "_store")

    def __init__(self, holder: str, store: RuntimeAuthorityStore) -> None:
        self._holder = holder
        self._store = store

    @property
    def holder(self) -> str:
        return self._holder

    def write(self, ts_ns: int, **updates: object) -> RuntimeSnapshot:
        """Write updates — canonical fields go to kernel, rest stay local."""
        return self._store._apply_write(self._holder, ts_ns, updates)


# ---------------------------------------------------------------------------
# RuntimeAuthorityStore — kernel-backed shim
# ---------------------------------------------------------------------------

AUTHORIZED_WRITERS: Final[frozenset[str]] = frozenset(
    {
        "governance_engine",
        "operator_interface_bridge",
        "execution_fabric",
        "system_engine",
    }
)

# Canonical fields that are forwarded to SystemKernel on write.
_KERNEL_FIELDS = frozenset({"system_mode", "freeze_active", "live_execution_blocked"})

ChangeCallback = Callable[[RuntimeSnapshot, RuntimeSnapshot], None]


class RuntimeAuthorityStore:
    """Kernel-backed authority shim.

    Retains the same public interface as the pre-migration store so
    fabric components compile unchanged.  All canonical state is
    delegated to :class:`SystemKernel`; operational fields (positions,
    health, exposure) are kept locally until migrated.
    """

    def __init__(
        self,
        *,
        initial: RuntimeSnapshot | None = None,
        kernel: SystemKernel | None = None,
    ) -> None:
        self._local: RuntimeSnapshot = initial or RuntimeSnapshot()
        self._kernel = kernel
        self._lock = RLock()
        self._callbacks: list[ChangeCallback] = []

    def bind_kernel(self, kernel: SystemKernel) -> None:
        """Bind a SystemKernel after construction (for lazy boot)."""
        self._kernel = kernel

    # --- Read ---

    @property
    def snapshot(self) -> RuntimeSnapshot:
        """Build a RuntimeSnapshot merging kernel + local state."""
        if self._kernel is None:
            return self._local
        ks = self._kernel.snapshot
        return replace(
            self._local,
            version=ks.version,
            ts_ns=ks.ts_ns,
            system_mode=ks.mode.value,
            freeze_active=ks.freeze_active,
            live_execution_blocked=ks.live_execution_blocked,
        )

    @property
    def version(self) -> int:
        if self._kernel is not None:
            return self._kernel.snapshot.version
        return self._local.version

    # --- Writer token issuance ---

    def issue_writer_token(self, holder: str) -> WriterToken:
        if holder not in AUTHORIZED_WRITERS:
            msg = (
                f"'{holder}' is not authorized to write RuntimeAuthority."
                f" Authorized: {sorted(AUTHORIZED_WRITERS)}"
            )
            raise PermissionError(msg)
        return WriterToken(holder, self)

    # --- Write (serialized) ---

    def _apply_write(
        self, holder: str, ts_ns: int, updates: dict[str, object]
    ) -> RuntimeSnapshot:
        with self._lock:
            old = self.snapshot

            valid_fields = set(RuntimeSnapshot.__dataclass_fields__)
            invalid = set(updates) - valid_fields - {"version", "ts_ns"}
            if invalid:
                msg = f"Invalid fields: {invalid}. Valid: {sorted(valid_fields)}"
                raise ValueError(msg)

            # Forward canonical fields to SystemKernel when bound
            if self._kernel is not None:
                mode_val = updates.get("system_mode")
                if mode_val is not None:
                    from core.contracts.governance import SystemMode

                    try:
                        self._kernel.transition_mode(
                            SystemMode(str(mode_val)),
                            reason=f"authority_write:{holder}",
                        )
                    except (ValueError, KeyError):
                        _logger.warning("Unknown mode %r from %s", mode_val, holder)

                freeze_val = updates.get("freeze_active")
                if freeze_val is not None:
                    self._kernel.set_freeze(
                        bool(freeze_val),
                        reason=f"authority_write:{holder}",
                    )

                exec_val = updates.get("live_execution_blocked")
                if exec_val is not None:
                    self._kernel.set_execution_blocked(bool(exec_val))

                # When kernel is bound, only local (non-kernel) fields go to _local
                local_updates = {
                    k: v
                    for k, v in updates.items()
                    if k in valid_fields and k not in _KERNEL_FIELDS
                }
            else:
                # No kernel — all valid fields go to _local (backward compat)
                local_updates = {
                    k: v for k, v in updates.items() if k in valid_fields
                }

            if local_updates or ts_ns != self._local.ts_ns:
                self._local = replace(
                    self._local,
                    version=self._local.version + 1,
                    ts_ns=ts_ns,
                    **local_updates,
                )

            new = self.snapshot

            for cb in self._callbacks:
                cb(old, new)

            return new

    # --- Subscriptions ---

    def subscribe(self, callback: ChangeCallback) -> None:
        self._callbacks.append(callback)

    def unsubscribe(self, callback: ChangeCallback) -> None:
        self._callbacks.remove(callback)

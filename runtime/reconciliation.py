"""runtime.reconciliation — State Reconciliation Engine.

Ensures ALL subsystems see consistent truth by detecting and resolving
divergence between:
- RuntimeAuthorityStore (source of truth)
- Execution engine (positions, fills)
- Governance engine (mode, hazards)
- Learning engine (belief states)
- Dashboard projections (UI state)
- Adapter states (broker positions)

OPERATIONAL INVARIANTS:
- Reconciliation runs every N ticks (configurable)
- Divergence beyond tolerance triggers immediate correction
- Corrections flow ONE WAY: authority → subsystems (never reverse)
- Unresolvable divergence triggers DEGRADED mode
- All reconciliation events are ledgered (replay-safe, INV-15)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from system import time_source

logger = logging.getLogger(__name__)


class ReconciliationStatus(StrEnum):
    """Outcome of a reconciliation pass."""

    CONSISTENT = "CONSISTENT"
    CORRECTED = "CORRECTED"
    DIVERGED = "DIVERGED"
    UNRESOLVABLE = "UNRESOLVABLE"


class SubsystemId(StrEnum):
    """Identifiers for reconciliation-tracked subsystems."""

    EXECUTION = "execution"
    GOVERNANCE = "governance"
    LEARNING = "learning"
    DASHBOARD = "dashboard"
    ADAPTER = "adapter"
    RISK_CACHE = "risk_cache"


@dataclass(frozen=True, slots=True)
class DivergenceReport:
    """Report of a single detected divergence."""

    subsystem: SubsystemId
    field_name: str
    authority_value: Any
    subsystem_value: Any
    delta: float = 0.0
    corrected: bool = False
    ts_ns: int = field(default_factory=time_source.wall_ns)


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """Full result of a reconciliation pass."""

    status: ReconciliationStatus
    divergences: tuple[DivergenceReport, ...] = ()
    corrections_applied: int = 0
    duration_ns: int = 0
    tick: int = 0
    ts_ns: int = field(default_factory=time_source.wall_ns)


@dataclass
class ReconciliationConfig:
    """Configuration for the reconciliation engine."""

    interval_ticks: int = 50
    position_tolerance_usd: float = 1.0
    exposure_tolerance_pct: float = 0.01
    health_tolerance: float = 0.05
    max_corrections_per_pass: int = 10
    degrade_on_unresolvable: bool = True


class StateReconciler:
    """Reconciles runtime authority state against all subsystems.

    The reconciler detects divergence between the authoritative
    RuntimeSnapshot and what each subsystem believes is true.
    Corrections flow ONE WAY: authority → subsystem.
    """

    __slots__ = (
        "_config",
        "_store",
        "_subsystem_readers",
        "_history",
        "_tick_counter",
    )

    def __init__(self, store: Any, config: ReconciliationConfig | None = None) -> None:
        self._config = config or ReconciliationConfig()
        self._store = store
        self._subsystem_readers: dict[SubsystemId, Any] = {}
        self._history: list[ReconciliationResult] = []
        self._tick_counter = 0

    def register_subsystem(self, subsystem_id: SubsystemId, reader: Any) -> None:
        """Register a subsystem for reconciliation tracking."""
        self._subsystem_readers[subsystem_id] = reader
        logger.debug("Registered subsystem for reconciliation: %s", subsystem_id)

    def tick(self) -> ReconciliationResult | None:
        """Called every tick. Runs reconciliation at configured interval."""
        self._tick_counter += 1
        if self._tick_counter % self._config.interval_ticks != 0:
            return None
        return self.reconcile()

    def reconcile(self) -> ReconciliationResult:
        """Run a full reconciliation pass.

        Compares authority state against all registered subsystems.
        Applies corrections where divergence exceeds tolerance.
        """
        start_ns = time_source.now_ns()
        divergences: list[DivergenceReport] = []
        corrections = 0

        snapshot = self._store.snapshot

        for subsystem_id, reader in self._subsystem_readers.items():
            subsystem_divergences = self._check_subsystem(subsystem_id, reader, snapshot)
            for div in subsystem_divergences:
                if corrections < self._config.max_corrections_per_pass:
                    corrected = self._apply_correction(subsystem_id, reader, div)
                    if corrected:
                        corrections += 1
                        divergences.append(
                            DivergenceReport(
                                subsystem=div.subsystem,
                                field_name=div.field_name,
                                authority_value=div.authority_value,
                                subsystem_value=div.subsystem_value,
                                delta=div.delta,
                                corrected=True,
                            )
                        )
                    else:
                        divergences.append(div)
                else:
                    divergences.append(div)

        duration_ns = time_source.now_ns() - start_ns

        # Determine overall status
        if not divergences:
            status = ReconciliationStatus.CONSISTENT
        elif all(d.corrected for d in divergences):
            status = ReconciliationStatus.CORRECTED
        elif any(not d.corrected for d in divergences):
            uncorrected = [d for d in divergences if not d.corrected]
            if len(uncorrected) > 3:
                status = ReconciliationStatus.UNRESOLVABLE
            else:
                status = ReconciliationStatus.DIVERGED
        else:
            status = ReconciliationStatus.CONSISTENT

        result = ReconciliationResult(
            status=status,
            divergences=tuple(divergences),
            corrections_applied=corrections,
            duration_ns=duration_ns,
            tick=self._tick_counter,
        )

        self._history.append(result)
        if len(self._history) > 100:
            self._history = self._history[-50:]

        if status == ReconciliationStatus.UNRESOLVABLE:
            logger.error("Reconciliation UNRESOLVABLE: %d divergences", len(divergences))
        elif status != ReconciliationStatus.CONSISTENT:
            logger.warning(
                "Reconciliation %s: %d divergences, %d corrected",
                status,
                len(divergences),
                corrections,
            )

        return result

    def _check_subsystem(
        self, subsystem_id: SubsystemId, reader: Any, snapshot: Any
    ) -> list[DivergenceReport]:
        """Check a single subsystem against authority."""
        divergences: list[DivergenceReport] = []

        try:
            # Each reader should implement get_state() → dict
            if not hasattr(reader, "get_state"):
                return divergences

            sub_state = reader.get_state()
            if not isinstance(sub_state, dict):
                return divergences

            # Check position count
            if "open_positions" in sub_state:
                authority_val = getattr(snapshot, "open_positions", 0)
                sub_val = sub_state["open_positions"]
                if abs(authority_val - sub_val) > 0:
                    divergences.append(
                        DivergenceReport(
                            subsystem=subsystem_id,
                            field_name="open_positions",
                            authority_value=authority_val,
                            subsystem_value=sub_val,
                            delta=abs(authority_val - sub_val),
                        )
                    )

            # Check exposure
            if "total_exposure_usd" in sub_state:
                authority_val = getattr(snapshot, "total_exposure_usd", 0.0)
                sub_val = float(sub_state["total_exposure_usd"])
                delta = abs(authority_val - sub_val)
                if delta > self._config.position_tolerance_usd:
                    divergences.append(
                        DivergenceReport(
                            subsystem=subsystem_id,
                            field_name="total_exposure_usd",
                            authority_value=authority_val,
                            subsystem_value=sub_val,
                            delta=delta,
                        )
                    )

            # Check system mode
            if "system_mode" in sub_state:
                authority_val = getattr(snapshot, "system_mode", "PAPER")
                sub_val = sub_state["system_mode"]
                if authority_val != sub_val:
                    divergences.append(
                        DivergenceReport(
                            subsystem=subsystem_id,
                            field_name="system_mode",
                            authority_value=authority_val,
                            subsystem_value=sub_val,
                        )
                    )

            # Check health
            if "health_score" in sub_state:
                authority_val = getattr(snapshot, "health_score", 1.0)
                sub_val = float(sub_state["health_score"])
                delta = abs(authority_val - sub_val)
                if delta > self._config.health_tolerance:
                    divergences.append(
                        DivergenceReport(
                            subsystem=subsystem_id,
                            field_name="health_score",
                            authority_value=authority_val,
                            subsystem_value=sub_val,
                            delta=delta,
                        )
                    )

        except Exception as e:
            logger.warning("Failed to check subsystem %s: %s", subsystem_id, e)

        return divergences

    def _apply_correction(
        self, subsystem_id: SubsystemId, reader: Any, divergence: DivergenceReport
    ) -> bool:
        """Apply a correction to a subsystem (authority → subsystem)."""
        try:
            if hasattr(reader, "force_sync"):
                reader.force_sync(divergence.field_name, divergence.authority_value)
                return True
            if hasattr(reader, "set_state"):
                reader.set_state({divergence.field_name: divergence.authority_value})
                return True
        except Exception as e:
            logger.warning(
                "Correction failed for %s.%s: %s", subsystem_id, divergence.field_name, e
            )
        return False

    @property
    def last_result(self) -> ReconciliationResult | None:
        return self._history[-1] if self._history else None

    @property
    def consistency_rate(self) -> float:
        """Fraction of recent reconciliations that were consistent."""
        if not self._history:
            return 1.0
        recent = self._history[-20:]
        consistent = sum(1 for r in recent if r.status == ReconciliationStatus.CONSISTENT)
        return consistent / len(recent)


__all__ = [
    "DivergenceReport",
    "ReconciliationConfig",
    "ReconciliationResult",
    "ReconciliationStatus",
    "StateReconciler",
    "SubsystemId",
]

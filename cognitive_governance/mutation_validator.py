"""
cognitive_governance/mutation_validator.py
DIX VISION v42.2 — Mutation Validator

Gate for every proposed strategy mutation. A mutation must pass ALL of:

  1. REVERSIBILITY — a rollback snapshot of the pre-mutation state must
     exist before the mutation is approved. Irreversible mutations are
     blocked unconditionally.

  2. SCOPE BUDGET — a single mutation may modify at most MAX_PARAMS_PER_MUTATION
     parameters simultaneously. Coordinated multi-parameter changes
     above this threshold require operator approval.

  3. MAGNITUDE BOUNDS — each parameter change must stay within
     MAX_PARAM_DELTA_SIGMA standard deviations of the parameter's
     observed historical distribution.

  4. LINEAGE REQUIREMENT — the mutation must name a valid ancestor
     strategy_id. Orphaned mutations (no cited lineage) are rejected.

This is a gate, not an optimizer. It does not evaluate whether the
mutation is good — only whether it is safe to trial.
"""

from __future__ import annotations

import math
import threading
from collections import deque

from core.contracts.cognitive_governance import (
    CognitiveSeverity,
    CognitiveViolationKind,
    MutationValidationResult,
)
from state.ledger.event_store import append_event

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_PARAMS_PER_MUTATION = 5
MAX_PARAM_DELTA_SIGMA = 3.0

# Rolling history length for per-parameter distribution tracking
_PARAM_HISTORY_LEN = 200


class MutationValidator:
    """
    Gate for proposed strategy mutations.

    Checks reversibility (snapshot exists), scope budget, magnitude bounds,
    and lineage requirement before approving a mutation.
    """

    def __init__(self) -> None:
        # strategy_id → {"params": dict[str, float], "ts_ns": int}
        self._snapshots: dict[str, dict] = {}
        # param_name → deque of observed float values (cross-strategy)
        self._param_history: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_strategy_snapshot(
        self,
        strategy_id: str,
        params: dict[str, float],
        ts_ns: int,
    ) -> None:
        """
        Record the current parameter state for a strategy.

        This snapshot is the rollback anchor. Must be called BEFORE
        any mutation proposal for this strategy is validated.
        """
        with self._lock:
            self._snapshots[strategy_id] = {
                "params": dict(params),
                "ts_ns": ts_ns,
            }
            # Update per-parameter history for distribution tracking
            for param_name, value in params.items():
                hist = self._param_history.setdefault(
                    param_name, deque(maxlen=_PARAM_HISTORY_LEN)
                )
                hist.append(value)

    def validate_mutation(
        self,
        mutation_id: str,
        strategy_id: str,
        source: str,
        param_deltas: dict[str, float],
        lineage_id: str | None,
        ts_ns: int,
    ) -> MutationValidationResult:
        """
        Validate a proposed mutation.

        param_deltas: mapping of parameter name → proposed delta (absolute change).
        lineage_id: the parent strategy_id this mutation evolves from.

        Returns MutationValidationResult with approved=True only if all
        four gates pass.
        """
        with self._lock:
            snapshot_exists = strategy_id in self._snapshots
            param_history_snapshot = {
                k: list(v) for k, v in self._param_history.items()
            }

        violations: list[CognitiveViolationKind] = []
        detail_parts: list[str] = []
        reversible = True
        scope_exceeded = False

        # Gate 1: Reversibility
        if not snapshot_exists:
            reversible = False
            violations.append(CognitiveViolationKind.MUTATION_IRREVERSIBLE)
            detail_parts.append(
                f"no snapshot for strategy_id={strategy_id!r}; "
                "call register_strategy_snapshot() before mutating"
            )

        # Gate 2: Scope budget
        n_params = len(param_deltas)
        if n_params > MAX_PARAMS_PER_MUTATION:
            scope_exceeded = True
            violations.append(CognitiveViolationKind.MUTATION_OUT_OF_BUDGET)
            detail_parts.append(
                f"mutation touches {n_params} parameters "
                f"> MAX_PARAMS_PER_MUTATION={MAX_PARAMS_PER_MUTATION}"
            )

        # Gate 3: Magnitude bounds (per-parameter sigma check)
        for param_name, delta in param_deltas.items():
            hist = param_history_snapshot.get(param_name, [])
            if len(hist) >= 2:
                mean, std = self._distribution_stats(hist)
                if std > 0 and abs(delta) > MAX_PARAM_DELTA_SIGMA * std:
                    violations.append(CognitiveViolationKind.MUTATION_OUT_OF_BUDGET)
                    detail_parts.append(
                        f"param={param_name!r}: |delta|={abs(delta):.4f} "
                        f"> {MAX_PARAM_DELTA_SIGMA}σ={MAX_PARAM_DELTA_SIGMA * std:.4f}"
                    )

        # Gate 4: Lineage requirement
        if lineage_id is None:
            violations.append(CognitiveViolationKind.LINEAGE_GAP)
            detail_parts.append("mutation has no cited lineage_id (orphaned mutation)")

        approved = len(violations) == 0
        detail = "; ".join(detail_parts) if detail_parts else "OK"

        # Determine severity for the event
        if not reversible:
            severity = CognitiveSeverity.CRITICAL
        elif scope_exceeded:
            severity = CognitiveSeverity.HIGH
        elif violations:
            severity = CognitiveSeverity.WARNING
        else:
            severity = CognitiveSeverity.INFO

        append_event(
            "GOVERNANCE",
            "COGOV_MUTATION_VALIDATED",
            "cognitive_governance.mutation_validator",
            {
                "mutation_id": mutation_id,
                "strategy_id": strategy_id,
                "source": source,
                "approved": approved,
                "reversible": reversible,
                "scope_exceeded": scope_exceeded,
                "n_params": n_params,
                "lineage_id": lineage_id,
                "severity": severity.value,
                "violations": [v.value for v in violations],
                "detail": detail,
            },
        )

        return MutationValidationResult(
            ts_ns=ts_ns,
            mutation_id=mutation_id,
            source=source,
            approved=approved,
            reversible=reversible,
            scope_exceeded=scope_exceeded,
            violations=tuple(violations),
            detail=detail,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _distribution_stats(values: list[float]) -> tuple[float, float]:
        """Return (mean, std) for a list of floats."""
        n = len(values)
        if n == 0:
            return 0.0, 0.0
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / n
        return mean, math.sqrt(variance)


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: MutationValidator | None = None
_lock = threading.Lock()


def get_mutation_validator() -> MutationValidator:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = MutationValidator()
    return _instance


__all__ = ["MutationValidator", "get_mutation_validator"]

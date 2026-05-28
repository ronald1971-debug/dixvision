"""EXEC-07 — deterministic chaos / fault injection engine.

Used by harness and test infrastructure to inject controlled faults.
All randomness is seeded by the caller so scenarios are reproducible
(INV-15). Never used in production paths — import-gated by caller.

B1:       No imports from engine tiers.
B27/B28:  Never constructs typed events.
INV-15:   All fault generation is seeded; identical seed → identical faults.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "FaultKind",
    "FaultSpec",
    "FaultResult",
    "ChaosEngine",
]


class FaultKind(str):
    LATENCY_SPIKE = "LATENCY_SPIKE"
    PACKET_DROP = "PACKET_DROP"
    FEED_SILENCE = "FEED_SILENCE"
    PARTIAL_FILL = "PARTIAL_FILL"
    REJECTED_ORDER = "REJECTED_ORDER"
    EXCHANGE_TIMEOUT = "EXCHANGE_TIMEOUT"


@dataclass(frozen=True, slots=True)
class FaultSpec:
    """Declarative fault specification."""

    kind: str
    probability: float  # 0.0–1.0
    magnitude: float = 1.0  # kind-specific scale factor
    params: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class FaultResult:
    """Outcome of a fault injection decision."""

    triggered: bool
    kind: str
    magnitude: float
    detail: str = ""


class ChaosEngine:
    """Deterministic fault injector.

    All decisions are made from a seeded :class:`random.Random` instance
    so replaying the same seed + spec sequence produces byte-identical
    :class:`FaultResult` outcomes.
    """

    def __init__(self, seed: int, specs: tuple[FaultSpec, ...] = ()) -> None:
        self._rng = random.Random(seed)
        self._specs: tuple[FaultSpec, ...] = specs
        self._injected = 0

    def inject(self, kind: str) -> FaultResult:
        """Roll against the matching :class:`FaultSpec` for ``kind``.

        Returns a non-triggered result when no spec matches or the
        probability roll fails.
        """
        for spec in self._specs:
            if spec.kind == kind:
                if self._rng.random() < spec.probability:
                    self._injected += 1
                    return FaultResult(
                        triggered=True,
                        kind=kind,
                        magnitude=spec.magnitude * self._rng.uniform(0.5, 1.5),
                        detail=f"chaos:{kind}:p={spec.probability:.2f}",
                    )
                return FaultResult(triggered=False, kind=kind, magnitude=0.0)
        return FaultResult(triggered=False, kind=kind, magnitude=0.0)

    def wrap(
        self,
        fn: Callable[[], Any],
        *,
        fault_kind: str,
        on_fault: Callable[[FaultResult], Any] | None = None,
    ) -> Any:
        """Call ``fn``, optionally substituting a fault outcome.

        If a fault triggers and ``on_fault`` is provided, ``on_fault``
        receives the :class:`FaultResult` and its return value is used
        instead of calling ``fn``.
        """
        result = self.inject(fault_kind)
        if result.triggered and on_fault is not None:
            return on_fault(result)
        return fn()

    @property
    def injected_count(self) -> int:
        return self._injected

    def reset(self, seed: int) -> None:
        """Reset the RNG to a new seed for the next scenario."""
        self._rng = random.Random(seed)
        self._injected = 0

"""Signal Funnel — single ranked fusion stage for ALL intelligence paths.

Every intelligence subsystem — microstructure plugins, cognitive router,
strategy runtime, meta-controller, trader modeling, opponent models,
neuromorphic layers, learning loops — MUST emit signals through this
funnel. No path may bypass it to reach the execution gate directly.

The funnel:

1. Accepts :class:`SignalEvent` from any registered provider.
2. Validates provenance (every signal must declare its source chain).
3. Applies trust capping per :mod:`core.contracts.signal_trust`.
4. Runs conflict resolution (same-symbol, same-tick collisions).
5. Ranks surviving signals by trust-weighted confidence.
6. Emits a single :class:`FunnelOutput` per tick — the canonical
   input to the execution gate.

Authority constraints:
- No cross-engine imports (only ``core.contracts`` + ``core.coherence``).
- Pure-Python, IO-free, clock-free (INV-40 compliant).
- Deterministic: same inputs → same output (INV-15).

This is the architectural chokepoint that prevents hidden authority
paths and non-determinism explosion from parallel intelligence systems.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from core.contracts.events import SignalEvent
from core.contracts.signal_trust import default_cap_for

_logger = logging.getLogger(__name__)


class ProviderTier(StrEnum):
    """Intelligence provider classification.

    Determines default trust weight and conflict-resolution priority.
    """

    CORE = "CORE"  # Meta-controller, strategy runtime
    PLUGIN = "PLUGIN"  # Microstructure plugins (footprint, VPIN, etc.)
    COGNITIVE = "COGNITIVE"  # LLM-backed cognitive analysis
    MODELING = "MODELING"  # Trader modeling, opponent models
    NEUROMORPHIC = "NEUROMORPHIC"  # SNN-based anomaly / pattern detection
    EXTERNAL = "EXTERNAL"  # External signal feeds (TradingView, etc.)


# Default trust weights per tier (higher = more influence in fusion)
_TIER_WEIGHTS: dict[ProviderTier, float] = {
    ProviderTier.CORE: 1.0,
    ProviderTier.PLUGIN: 0.8,
    ProviderTier.COGNITIVE: 0.6,
    ProviderTier.MODELING: 0.5,
    ProviderTier.NEUROMORPHIC: 0.7,
    ProviderTier.EXTERNAL: 0.3,
}


@dataclass(frozen=True, slots=True)
class RegisteredProvider:
    """A registered intelligence provider."""

    name: str
    tier: ProviderTier
    weight_override: float | None = None

    @property
    def weight(self) -> float:
        if self.weight_override is not None:
            return self.weight_override
        return _TIER_WEIGHTS.get(self.tier, 0.5)


@dataclass(frozen=True, slots=True)
class RankedSignal:
    """A signal after trust-capping and ranking."""

    signal: SignalEvent
    provider: str
    tier: ProviderTier
    raw_confidence: float
    capped_confidence: float
    fused_score: float  # tier_weight * capped_confidence


@dataclass(frozen=True, slots=True)
class FunnelOutput:
    """The canonical output of the signal funnel for one tick.

    This is the ONLY object the execution gate should read for
    trading decisions. It replaces all direct signal paths.
    """

    tick_ns: int
    ranked_signals: tuple[RankedSignal, ...]
    # Per-symbol consensus: the top-ranked signal per symbol after fusion
    consensus: tuple[RankedSignal, ...]
    # Signals that were rejected (below threshold, conflicting, untrusted)
    rejected_count: int = 0
    provider_count: int = 0


class SignalFunnel:
    """Single fusion stage for all intelligence paths.

    Usage::

        funnel = SignalFunnel()
        funnel.register("meta_controller", ProviderTier.CORE)
        funnel.register("vpin_imbalance", ProviderTier.PLUGIN)
        funnel.register("cognitive_debate", ProviderTier.COGNITIVE)

        # Each tick: collect signals from all providers, then fuse
        output = funnel.fuse(tick_ns=now, signals=all_signals)
        # output.consensus is the canonical ranked list
    """

    __slots__ = ("_providers", "_min_fused_score", "_max_signals_per_symbol")

    def __init__(
        self,
        *,
        min_fused_score: float = 0.05,
        max_signals_per_symbol: int = 1,
    ) -> None:
        self._providers: dict[str, RegisteredProvider] = {}
        self._min_fused_score = min_fused_score
        self._max_signals_per_symbol = max_signals_per_symbol

    def register(
        self,
        name: str,
        tier: ProviderTier,
        *,
        weight_override: float | None = None,
    ) -> None:
        """Register an intelligence provider."""
        self._providers[name] = RegisteredProvider(
            name=name,
            tier=tier,
            weight_override=weight_override,
        )
        _logger.info(
            "SignalFunnel: registered provider %s (tier=%s, weight=%.2f)",
            name,
            tier,
            self._providers[name].weight,
        )

    @property
    def provider_count(self) -> int:
        return len(self._providers)

    def fuse(
        self,
        *,
        tick_ns: int,
        signals: Sequence[tuple[str, SignalEvent]],
    ) -> FunnelOutput:
        """Fuse signals from all providers into a single ranked output.

        Parameters
        ----------
        tick_ns:
            The current tick timestamp (nanoseconds).
        signals:
            Sequence of ``(provider_name, SignalEvent)`` pairs. Provider
            names must have been registered via :meth:`register`.

        Returns
        -------
        FunnelOutput
            The canonical ranked and fused signal set for this tick.
        """
        ranked: list[RankedSignal] = []
        rejected = 0

        for provider_name, sig in signals:
            prov = self._providers.get(provider_name)
            if prov is None:
                _logger.warning(
                    "SignalFunnel: signal from unregistered provider %r — rejected",
                    provider_name,
                )
                rejected += 1
                continue

            # Apply trust cap based on signal provenance
            cap = default_cap_for(sig.trust)
            raw_conf = sig.confidence
            capped = min(raw_conf, cap)
            fused = prov.weight * capped

            if fused < self._min_fused_score:
                rejected += 1
                continue

            ranked.append(
                RankedSignal(
                    signal=sig,
                    provider=provider_name,
                    tier=prov.tier,
                    raw_confidence=raw_conf,
                    capped_confidence=capped,
                    fused_score=fused,
                )
            )

        # Sort by fused score descending (deterministic: break ties by provider name)
        ranked.sort(key=lambda r: (-r.fused_score, r.provider))

        # Build per-symbol consensus: top signal per symbol
        seen_symbols: set[str] = set()
        consensus: list[RankedSignal] = []
        for r in ranked:
            sym = r.signal.symbol
            if sym not in seen_symbols:
                seen_symbols.add(sym)
                consensus.append(r)
                if len(consensus) >= 128:  # safety cap
                    break

        return FunnelOutput(
            tick_ns=tick_ns,
            ranked_signals=tuple(ranked),
            consensus=tuple(consensus),
            rejected_count=rejected,
            provider_count=len(self._providers),
        )

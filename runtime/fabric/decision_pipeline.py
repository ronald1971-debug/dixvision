"""Decision Pipeline — market event → signal → intent (CONVERGENCE PILLAR 2).

LEGACY: This pipeline uses the pre-convergence IndiraEngine path.
The canonical intelligence path is:

    MarketTick → IntelligenceEngine.run_meta_tick()
              → SignalFunnel.fuse()
              → FunnelOutput.consensus
              → ExecutionEngine.execute()

New code should use ``intelligence_engine.signal_funnel.SignalFunnel``
and the ``core.kernel.SystemKernel`` dispatch path. This module is
retained for backward compatibility with the ``RuntimeKernel`` legacy
loop and will be migrated in the next major version.

Pipeline:
    IngestedTick → IndiraEngine.process_tick() → confidence scoring → intent creation
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum, auto

from runtime.authority import RuntimeAuthorityStore
from runtime.fabric.ingestion_bus import IngestedTick


class SignalStrength(StrEnum):
    """Signal confidence categories."""

    NONE = auto()
    WEAK = auto()
    MODERATE = auto()
    STRONG = auto()


@dataclass(frozen=True, slots=True)
class DecisionSignal:
    """A trading signal produced by the intelligence engine."""

    symbol: str
    side: str  # BUY / SELL / HOLD
    strength: SignalStrength
    confidence: float
    source_engine: str
    rationale: str
    ts_ns: int


@dataclass(frozen=True, slots=True)
class ExecutionIntent:
    """An intent ready for governance review and execution routing."""

    intent_id: str
    symbol: str
    side: str
    notional_usd: float
    domain: str
    signal: DecisionSignal
    governance_signature: str | None = None
    ts_ns: int = 0


@dataclass(frozen=True, slots=True)
class PipelineMetrics:
    """Decision pipeline telemetry."""

    ticks_processed: int = 0
    signals_generated: int = 0
    intents_created: int = 0
    signals_filtered: int = 0


class DecisionPipeline:
    """Converts market ticks into execution intents.

    Delegates signal generation to IndiraEngine (the real intelligence
    engine) instead of using a placeholder. Reads RuntimeAuthority to
    determine freeze/capability state.
    """

    def __init__(self, *, store: RuntimeAuthorityStore) -> None:
        self._store = store
        self._metrics = PipelineMetrics()
        self._indira = None

    @property
    def metrics(self) -> PipelineMetrics:
        return self._metrics

    def _get_indira(self):
        """Lazily initialize IndiraEngine to avoid circular imports."""
        if self._indira is None:
            from mind.engine import IndiraEngine

            self._indira = IndiraEngine()
        return self._indira

    def process_tick(self, tick: IngestedTick) -> ExecutionIntent | None:
        """Process a market tick through the Indira decision engine.

        Returns an ExecutionIntent if the pipeline generates one,
        None if the tick produces no actionable signal.
        """
        snap = self._store.snapshot

        # Block all intent creation if frozen
        if snap.freeze_active:
            self._metrics = PipelineMetrics(
                ticks_processed=self._metrics.ticks_processed + 1,
                signals_generated=self._metrics.signals_generated,
                intents_created=self._metrics.intents_created,
                signals_filtered=self._metrics.signals_filtered + 1,
            )
            return None

        # Run through Indira intelligence engine
        indira = self._get_indira()
        market_data = {
            "signal": tick.price,
            "asset": tick.symbol,
            "price": tick.price,
            "data_quality": 0.95,
            "execution_confidence": 0.90,
            "strategy": "regime_adaptive",
        }
        ev = indira.process_tick(market_data)

        # Classify signal strength from Indira's output
        if ev.event_type == "HOLD" or ev.event_type == "DELEGATE":
            strength = SignalStrength.NONE
        elif ev.confidence >= 0.8:
            strength = SignalStrength.STRONG
        elif ev.confidence >= 0.5:
            strength = SignalStrength.MODERATE
        else:
            strength = SignalStrength.WEAK

        signal = DecisionSignal(
            symbol=tick.symbol,
            side=ev.side if ev.side != "NONE" else "HOLD",
            strength=strength,
            confidence=ev.confidence,
            source_engine="indira",
            rationale=f"{ev.event_type}:{ev.strategy}",
            ts_ns=tick.ts_ns,
        )

        # No actionable signal
        if signal.strength == SignalStrength.NONE or signal.side == "HOLD":
            self._metrics = PipelineMetrics(
                ticks_processed=self._metrics.ticks_processed + 1,
                signals_generated=self._metrics.signals_generated,
                intents_created=self._metrics.intents_created,
                signals_filtered=self._metrics.signals_filtered,
            )
            return None

        self._metrics = PipelineMetrics(
            ticks_processed=self._metrics.ticks_processed + 1,
            signals_generated=self._metrics.signals_generated + 1,
            intents_created=self._metrics.intents_created,
            signals_filtered=self._metrics.signals_filtered,
        )

        # Check capability tier
        if snap.current_capability_tier < 3:
            return None

        # Create intent
        intent = ExecutionIntent(
            intent_id=f"intent-{uuid.uuid4().hex[:12]}",
            symbol=tick.symbol,
            side=signal.side,
            notional_usd=ev.size_usd if ev.size_usd > 0 else tick.price * tick.volume,
            domain="NORMAL",
            signal=signal,
            ts_ns=tick.ts_ns,
        )

        self._metrics = PipelineMetrics(
            ticks_processed=self._metrics.ticks_processed,
            signals_generated=self._metrics.signals_generated,
            intents_created=self._metrics.intents_created + 1,
            signals_filtered=self._metrics.signals_filtered,
        )

        return intent

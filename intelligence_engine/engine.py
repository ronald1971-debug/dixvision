"""IntelligenceEngine — RUNTIME-ENGINE-01 (Phase E2 + Wave 1 wiring).

Phase E2 wired the first concrete intelligence plugin (IND-L02 market
microstructure) under the ``microstructure`` slot. Wave 1 adds the
optional :class:`MetaControllerHotPath` integration so that a single
:meth:`run_meta_tick` call:

1. drives all enabled microstructure plugins from a :class:`MarketTick`,
2. appends the emitted signals to a bounded rolling window owned by
   the engine,
3. invokes :meth:`MetaControllerHotPath.step` with the rolling window
   plus a caller-supplied :class:`RuntimeContext` (perf / risk /
   drift / latency / ``vol_spike_z`` / ``elapsed_ns``),
4. returns ``(signals, decision, ledger)``.

The engine still satisfies :class:`RuntimeEngine`:

* :meth:`process` is bus-side. It is a pure passthrough for
  ``SignalEvent``s today (Phase E0 behaviour preserved); other event
  kinds are silently ignored at the contract layer.
* :meth:`on_market` is the input-side. ``MarketTick`` is **not** a
  canonical bus event (INV-08); it flows from a data feed into the
  engine, drives the active microstructure plugins, and the engine
  collects their :class:`SignalEvent` outputs.
* :meth:`run_meta_tick` is opt-in — it requires a
  :class:`MetaControllerHotPath` to have been passed at construction.

Plugin-level SHADOW was demolished by SHADOW-DEMOLITION-01: a plugin
is either ``DISABLED`` (skipped) or ``ACTIVE`` (its signals flow
into the conflict resolver). Signals-on/execution-off behaviour now
lives at the system-mode layer only.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping, Sequence

from core.contracts.engine import (
    EngineTier,
    HealthState,
    HealthStatus,
    MicrostructurePlugin,
    Plugin,
    PluginLifecycle,
    RuntimeEngine,
)
from core.contracts.events import Event, SignalEvent, SystemEvent
from core.contracts.market import MarketTick
from intelligence_engine.cognitive import observability_emitter as _obs
from intelligence_engine.learning_gate import LearningGate
from intelligence_engine.meta_controller import MetaControllerHotPath
from intelligence_engine.meta_controller.policy import ExecutionDecision
from intelligence_engine.runtime_context import RuntimeContext

DEFAULT_SIGNAL_WINDOW_SIZE = 32


class IntelligenceEngine(RuntimeEngine):
    name: str = "intelligence"
    tier: EngineTier = EngineTier.RUNTIME

    def __init__(
        self,
        microstructure_plugins: Sequence[MicrostructurePlugin] | None = None,
        plugin_slots: Mapping[str, Sequence[Plugin]] | None = None,
        *,
        meta_controller_hot_path: MetaControllerHotPath | None = None,
        signal_window_size: int = DEFAULT_SIGNAL_WINDOW_SIZE,
        learning_gate: LearningGate | None = None,
    ) -> None:
        if signal_window_size <= 0:
            raise ValueError("signal_window_size must be > 0")
        self._microstructure: tuple[MicrostructurePlugin, ...] = tuple(microstructure_plugins or ())
        slots: dict[str, Sequence[object]] = dict(plugin_slots or {})
        # Surface the typed microstructure plugins under the same slot
        # exposed in registry/plugins.yaml so check_self() reports them.
        slots["microstructure"] = self._microstructure
        self.plugin_slots = slots  # type: ignore[assignment]

        self._meta_controller_hot_path = meta_controller_hot_path
        self._signal_window: deque[SignalEvent] = deque(maxlen=signal_window_size)
        self._last_confidence: float = 0.0  # tracks confidence for shift detection
        self._last_regime: str = "UNKNOWN"  # tracks regime for belief evolution detection
        self._last_regime_confidence: float = 0.0
        # PR-DEV-B — Operator Master Development Mode learning gate.
        # ``None`` is the migration sentinel (fail-open) so pre-PR-DEV-B
        # offline tests that construct an engine without a governance
        # runtime in scope retain their previous unconditional-emit
        # behaviour. Production wiring at ``ui.server._State`` injects
        # a :class:`LearningGate` whose ``policy_supplier`` reads the
        # live ``DevelopmentModePolicy`` so an operator flip via
        # ``POST /api/operator/development-mode {enabled: false}``
        # short-circuits the next ``on_market`` / ``run_meta_tick``.
        self._learning_gate = learning_gate

    @property
    def microstructure_plugins(self) -> tuple[MicrostructurePlugin, ...]:
        return self._microstructure

    @property
    def meta_controller_hot_path(self) -> MetaControllerHotPath | None:
        return self._meta_controller_hot_path

    @property
    def signal_window(self) -> tuple[SignalEvent, ...]:
        """Snapshot of the rolling signal window. Read-only."""
        return tuple(self._signal_window)

    @property
    def learning_gate(self) -> LearningGate | None:
        """PR-DEV-B — the operator-controlled learning gate, or
        ``None`` if the engine was constructed without one (migration
        sentinel; fail-open)."""
        return self._learning_gate

    def set_learning_gate(self, gate: LearningGate | None) -> None:
        """PR-DEV-B — replace the active :class:`LearningGate`.

        Mirrors :meth:`ExecutionEngine.set_development_mode_policy`:
        production wiring uses this from the boot-time governance
        builder so the gate is installed *after* the engine has been
        constructed (the engine itself lives under the runtime tier,
        but the policy supplier must close over governance state
        without violating L1/L2/L3 import direction).
        """
        self._learning_gate = gate

    def on_market(self, tick: MarketTick) -> tuple[SignalEvent, ...]:
        """Run all enabled microstructure plugins against ``tick``.

        Returns the concatenated, in-order tuple of emitted signals.

        Wave 1: the engine also appends the emitted signals to its
        rolling window so a subsequent :meth:`run_meta_tick` sees a
        coherent recent-signal context.

        PR-DEV-B: when the operator has flipped
        :attr:`DevelopmentModePolicy.development_enabled` to
        ``False`` (via ``POST /api/operator/development-mode`` or the
        boot-time ``DIXVISION_DEVELOPMENT_MODE=false`` pin), the
        configured :class:`LearningGate` closes and this method
        returns an empty tuple. No plugins are invoked, no signals
        are appended to the rolling window, and no audit row is
        emitted from this method (the audit row is emitted by the
        operator route at flip time, not on every silent tick).
        """
        if self._learning_gate is not None and self._learning_gate.is_closed():
            return ()
        out: list[SignalEvent] = []
        for plugin in self._microstructure:
            if plugin.lifecycle is PluginLifecycle.DISABLED:
                continue
            for sig in plugin.on_tick(tick):
                out.append(sig)
        emitted = tuple(out)
        for sig in emitted:
            self._signal_window.append(sig)
        return emitted

    def run_meta_tick(
        self,
        *,
        tick: MarketTick,
        context: RuntimeContext,
        extra_signals: Iterable[SignalEvent] = (),
    ) -> tuple[
        tuple[SignalEvent, ...],
        ExecutionDecision,
        tuple[SystemEvent, ...],
    ]:
        """Drive plugins, advance the meta-controller, and return the
        full per-tick triple ``(signals, decision, ledger)``.

        The engine itself does not consult any clock; ``elapsed_ns``
        and ``tick.ts_ns`` are caller-supplied so replay determinism
        (INV-15) is preserved.

        Args:
            tick: The :class:`MarketTick` to drive plugins from.
            context: Per-tick runtime scalars
                (:class:`RuntimeContext`).
            extra_signals: Optional additional signals from non-
                microstructure intelligence plugins (e.g. plugins owned
                by a higher-level orchestrator) to be appended to the
                rolling window before the meta-controller step. They
                are returned as part of the emitted signals tuple as
                well, after the microstructure-emitted ones.

        Returns:
            ``(signals, decision, ledger)`` where:

            * ``signals`` are the freshly emitted signals (microstructure
              + ``extra_signals``) in deterministic order.
            * ``decision`` is the primary :class:`ExecutionDecision` from
              the meta-controller.
            * ``ledger`` is the four-event :class:`SystemEvent` ledger
              (BELIEF_STATE_SNAPSHOT → PRESSURE_VECTOR_SNAPSHOT →
              META_AUDIT → optional META_DIVERGENCE).

        Raises:
            RuntimeError: if no :class:`MetaControllerHotPath` was
                passed at construction.
        """
        hot = self._meta_controller_hot_path
        if hot is None:
            raise RuntimeError(
                "IntelligenceEngine.run_meta_tick requires "
                "meta_controller_hot_path to be configured at "
                "construction time."
            )

        emitted = self.on_market(tick)
        extras = tuple(extra_signals)
        for sig in extras:
            self._signal_window.append(sig)

        decision, ledger = hot.step(
            ts_ns=tick.ts_ns,
            signals=tuple(self._signal_window),
            perf=context.perf,
            risk=context.risk,
            drift=context.drift,
            latency=context.latency,
            vol_spike_z=context.vol_spike_z,
            elapsed_ns=context.elapsed_ns,
        )
        self._emit_cognition_events(tick.ts_ns, decision)
        return emitted + extras, decision, ledger

    def _emit_cognition_events(self, ts_ns: int, decision: ExecutionDecision) -> None:
        """Best-effort cognitive observability emission. Never raises."""
        new_conf = decision.confidence
        _obs.emit_thought_stream(
            ts_ns=ts_ns,
            reasoning_step="meta_controller_tick",
            context=(
                f"side={decision.side.value} "
                f"size={decision.size_fraction:.3f} "
                f"fallback={decision.fallback}"
            ),
            confidence=new_conf,
            inputs=(f"signal_window_size={len(self._signal_window)}",),
            conclusion=(
                f"ExecutionDecision: {decision.side.value} "
                f"confidence={new_conf:.3f}"
            ),
        )
        _obs.emit_confidence_shift(
            ts_ns=ts_ns,
            subject="meta_controller.composite_confidence",
            old_confidence=self._last_confidence,
            new_confidence=new_conf,
            driver="meta_controller_tick",
        )
        self._last_confidence = new_conf
        # Emit BeliefEvolutionEvent when the committed regime transitions.
        hot = self._meta_controller_hot_path
        if hot is not None:
            rs = hot.state.router_state
            new_regime = rs.current_regime.value
            new_regime_conf = rs.current_confidence
            if new_regime != self._last_regime:
                _obs.emit_belief_evolution(
                    ts_ns=ts_ns,
                    belief_id=f"regime_belief_{ts_ns}",
                    subject="market.committed_regime",
                    old_value=self._last_regime_confidence if self._last_regime != "UNKNOWN" else None,
                    new_value=new_regime_conf,
                    driver=f"regime_transition:{self._last_regime}→{new_regime}",
                    confidence=new_regime_conf,
                )
                self._last_regime = new_regime
                self._last_regime_confidence = new_regime_conf
                # Emit causal chain tracing the reasoning behind the transition.
                try:
                    from intelligence_engine.cognitive.observability_emitter import (
                        emit_causal_chain,
                    )
                    emit_causal_chain(
                        ts_ns=ts_ns,
                        hypothesis=(
                            f"Market regime shifted to {new_regime} "
                            f"(confidence {new_regime_conf:.2f})"
                        ),
                        causes=(
                            f"prior_regime={self._last_regime if self._last_regime != new_regime else 'UNKNOWN'}",
                            f"decision_side={decision.side.value}",
                            f"composite_confidence={new_conf:.3f}",
                            f"signal_window={len(self._signal_window)}",
                        ),
                        effects=(
                            f"committed_regime={new_regime}",
                            f"position_bias={decision.side.value}",
                            f"size_fraction={decision.size_fraction:.3f}",
                        ),
                        confidence=new_regime_conf,
                        evidence_count=len(self._signal_window),
                    )
                except Exception:  # pragma: no cover
                    pass
        # Emit a market-grounded ThoughtRuntime tick so INDIRA's inner
        # reasoning loop reflects the live meta-controller decision.
        try:
            from intelligence_engine.cognitive.thought_runtime import get_thought_runtime
            regime_str = self._last_regime
            get_thought_runtime().tick(
                ts_ns=ts_ns,
                context_override=(
                    f"regime={regime_str} "
                    f"confidence={new_conf:.3f} "
                    f"side={decision.side.value} "
                    f"size={decision.size_fraction:.3f} "
                    f"window={len(self._signal_window)}"
                ),
                conclusion_override=(
                    f"Decision confirmed: {decision.side.value} "
                    f"confidence={new_conf:.3f} regime={regime_str}"
                ),
                confidence_override=new_conf,
            )
        except Exception:  # pragma: no cover
            pass

    def process(self, event: Event) -> Sequence[Event]:
        # Bus-side passthrough; SignalEvents flow on the canonical bus.
        if isinstance(event, SignalEvent):
            return (event,)
        return ()

    def check_self(self) -> HealthStatus:
        plugin_states: dict[str, dict[str, HealthState]] = {}
        for slot, plugins in self.plugin_slots.items():
            slot_states: dict[str, HealthState] = {}
            for p in plugins:
                try:
                    slot_states[p.name] = p.check_self().state
                except Exception:  # pragma: no cover - defensive
                    slot_states[p.name] = HealthState.FAIL
            plugin_states[slot] = slot_states

        if not self._microstructure:
            detail = "Phase E2 — no microstructure plugins loaded"
        else:
            modes = ",".join(f"{p.name}:{p.lifecycle}" for p in self._microstructure)
            detail = f"Phase E2 — microstructure=[{modes}]"

        if self._meta_controller_hot_path is not None:
            detail = f"{detail} meta_controller=wired"

        return HealthStatus(
            state=HealthState.OK,
            detail=detail,
            plugin_states=plugin_states,
        )


def register_default_providers(
    funnel: object,
    *,
    plugins: Sequence[MicrostructurePlugin] = (),
) -> None:
    """Register all standard intelligence providers with a SignalFunnel.

    Called at boot time to ensure every intelligence path flows through
    the funnel. The ``funnel`` is typed as ``object`` to avoid a
    circular import (``signal_funnel`` imports ``core.contracts`` only).

    Usage::

        from intelligence_engine.signal_funnel import SignalFunnel, ProviderTier

        funnel = SignalFunnel()
        register_default_providers(funnel, plugins=engine.microstructure_plugins)
    """
    from intelligence_engine.signal_funnel import ProviderTier

    register = getattr(funnel, "register", None)
    if register is None:
        return

    # Core: meta-controller (confidence + regime + execution policy)
    register("meta_controller", ProviderTier.CORE)
    # Core: strategy runtime (conflict resolver + orchestrator)
    register("strategy_runtime", ProviderTier.CORE)

    # Plugins: each microstructure plugin
    for p in plugins:
        register(f"plugin:{p.name}", ProviderTier.PLUGIN)

    # Cognitive: LLM-backed debate graph
    register("cognitive_debate", ProviderTier.COGNITIVE)
    # Modeling: trader imitation + opponent models
    register("trader_modeling", ProviderTier.MODELING)
    register("opponent_model", ProviderTier.MODELING)
    # Neuromorphic: SNN-based detectors
    register("neuromorphic_snn", ProviderTier.NEUROMORPHIC)
    register("neuromorphic_anomaly", ProviderTier.NEUROMORPHIC)
    # External: signal feeds
    register("external_feeds", ProviderTier.EXTERNAL)


__all__ = [
    "DEFAULT_SIGNAL_WINDOW_SIZE",
    "IntelligenceEngine",
    "register_default_providers",
]

"""AGT-05 — multi-regime swing trader (5th AGT-XX agent).

A more sophisticated swing agent than AGT-02. Where AGT-02 uses a plain
two-window SMA crossover, AGT-05 combines:

1. **Chandelier Exit stops** — ATR-based trailing stops that keep the
   agent out of the market when price has violated the stop level. The
   Chandelier Exit is defined as:

       long_stop  = rolling_high(atr_period) - atr_multiplier * ATR
       short_stop = rolling_low(atr_period)  + atr_multiplier * ATR

   If the latest mid price is below ``long_stop`` (when long biased) or
   above ``short_stop`` (when short biased), the regime is treated as
   stop-violated and the agent emits HOLD.

2. **Regime filter** — the agent only trades in TREND_UP or TREND_DOWN
   regimes (fast SMA > slow SMA + threshold, or vice versa). RANGE and
   VOL_SPIKE regimes produce HOLD to avoid churn in directionless
   markets.

3. **Minimum hold period** — once a direction is committed, the agent
   will not switch direction until ``min_hold_ticks`` ticks have elapsed
   since the last non-HOLD decision, preventing rapid flip-flop.

INV-54 invariants enforced via
:class:`~intelligence_engine.agents._base.AgentBase`:

* :meth:`state_snapshot` is pure (no clock, no PRNG, no IO).
* :meth:`recent_decisions` is O(1) per call (bounded ring buffer).
* ``state_snapshot`` keys subset
  ``registry/agent_state_keys.yaml#AGT-05-swing-trader``.
* ``rationale_tags`` drawn from ``registry/agent_rationale_tags.yaml``.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field

from core.contracts.agent import AgentDecisionTrace, AgentIntrospection
from core.contracts.events import Side, SignalEvent
from core.contracts.market import MarketTick
from intelligence_engine.agents._base import AgentBase

_BUY = "BUY"
_SELL = "SELL"
_HOLD = "HOLD"

# Regime labels produced by the internal fast/slow SMA classification.
_TREND_UP = "TREND_UP"
_TREND_DOWN = "TREND_DOWN"
_RANGE = "RANGE"
# VOL_SPIKE is detected via a simplistic ATR z-score check.
_VOL_SPIKE = "VOL_SPIKE"


def _mean(seq: list[float]) -> float:
    return sum(seq) / len(seq) if seq else 0.0


def _true_range(high: float, low: float, prev_close: float) -> float:
    """Wilder's true range: max(H-L, |H-Cprev|, |L-Cprev|)."""
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


@dataclass
class SwingTraderAgent(AgentBase, AgentIntrospection):
    """Multi-regime swing trader (AGT-05).

    Attributes
    ----------
    agent_id:
        Stable INV-54 identifier.
    fast_window:
        Fast SMA window (ticks).
    slow_window:
        Slow SMA window (ticks). Must be > fast_window.
    atr_period:
        Rolling period for ATR and Chandelier Exit computation.
    atr_multiplier:
        Multiplier for ATR in the Chandelier Exit formula.
    regime_threshold_bps:
        Minimum fast-vs-slow spread in basis points to declare
        TREND_UP or TREND_DOWN. Smaller spread → RANGE.
    vol_spike_atr_z:
        Z-score threshold above which the current ATR is classified
        as a VOL_SPIKE (uses rolling mean ATR as baseline).
    min_hold_ticks:
        Minimum ticks between directional flips.
    min_confidence:
        Confidence floor below which a directional signal is
        downgraded to HOLD.
    ring_capacity:
        Ring buffer capacity for :meth:`recent_decisions`.
    """

    agent_id: str = "AGT-05-swing-trader"
    fast_window: int = 12
    slow_window: int = 36
    atr_period: int = 14
    atr_multiplier: float = 2.5
    regime_threshold_bps: float = 3.0
    vol_spike_atr_z: float = 2.5
    min_hold_ticks: int = 3
    min_confidence: float = 0.05
    ring_capacity: int = 64

    # Internal state — not part of the public API.
    _mid_window: deque[float] = field(init=False, repr=False)
    _tr_window: deque[float] = field(init=False, repr=False)
    _high_window: deque[float] = field(init=False, repr=False)
    _low_window: deque[float] = field(init=False, repr=False)
    _prev_close: float = field(default=0.0, init=False, repr=False)
    _ticks_since_direction_change: int = field(default=0, init=False, repr=False)
    _last_committed_direction: str = field(default=_HOLD, init=False, repr=False)
    _last_decision_direction: str = field(default=_HOLD, init=False, repr=False)
    _last_decision_confidence: float = field(default=0.0, init=False, repr=False)
    _last_decision_ts_ns: int = field(default=0, init=False, repr=False)
    _last_regime: str = field(default=_RANGE, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.fast_window < 2:
            raise ValueError("fast_window must be >= 2")
        if self.slow_window <= self.fast_window:
            raise ValueError("slow_window must be > fast_window")
        if self.atr_period < 1:
            raise ValueError("atr_period must be >= 1")
        if self.atr_multiplier <= 0.0:
            raise ValueError("atr_multiplier must be > 0")
        if self.regime_threshold_bps < 0.0:
            raise ValueError("regime_threshold_bps must be >= 0")
        if self.vol_spike_atr_z <= 0.0:
            raise ValueError("vol_spike_atr_z must be > 0")
        if self.min_hold_ticks < 0:
            raise ValueError("min_hold_ticks must be >= 0")
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("min_confidence must be in [0, 1]")
        AgentBase.__init__(self, self.agent_id, self.ring_capacity)
        self._mid_window = deque(maxlen=self.slow_window)
        self._tr_window = deque(maxlen=self.atr_period)
        self._high_window = deque(maxlen=self.atr_period)
        self._low_window = deque(maxlen=self.atr_period)

    # --- inputs --------------------------------------------------------

    def observe_tick(self, tick: MarketTick) -> None:
        """Update internal rolling buffers from a market tick."""
        if tick.bid <= 0.0 or tick.ask <= 0.0 or tick.ask < tick.bid:
            return
        mid = 0.5 * (tick.bid + tick.ask)
        if mid <= 0.0:
            return

        high = tick.ask
        low = tick.bid
        close = mid

        tr = _true_range(high, low, self._prev_close if self._prev_close > 0.0 else close)
        self._mid_window.append(mid)
        self._tr_window.append(tr)
        self._high_window.append(high)
        self._low_window.append(low)
        self._prev_close = close

    # --- internals -----------------------------------------------------

    def _fast_sma(self) -> float:
        items = list(self._mid_window)
        recent = items[-self.fast_window :]
        return _mean(recent)

    def _slow_sma(self) -> float:
        items = list(self._mid_window)
        return _mean(items)

    def _current_atr(self) -> float:
        trs = list(self._tr_window)
        return _mean(trs) if trs else 0.0

    def _classify_regime(self, fast: float, slow: float) -> str:
        """Classify regime as TREND_UP, TREND_DOWN, RANGE, or VOL_SPIKE."""
        if slow <= 0.0:
            return _RANGE

        # VOL_SPIKE: current ATR is vol_spike_atr_z standard deviations
        # above mean ATR. Use simple mean/std over the tr_window.
        trs = list(self._tr_window)
        if len(trs) >= 3:
            atr_mean = _mean(trs)
            atr_sq = sum((t - atr_mean) ** 2 for t in trs) / len(trs)
            atr_std = atr_sq ** 0.5
            current_atr = trs[-1] if trs else 0.0
            if atr_std > 0.0 and (current_atr - atr_mean) / atr_std > self.vol_spike_atr_z:
                return _VOL_SPIKE

        spread_bps = (fast - slow) / slow * 10_000.0
        if spread_bps > self.regime_threshold_bps:
            return _TREND_UP
        if spread_bps < -self.regime_threshold_bps:
            return _TREND_DOWN
        return _RANGE

    def _chandelier_stop_violated(self, regime: str, mid: float) -> bool:
        """Return True if the Chandelier Exit stop has been breached."""
        atr = self._current_atr()
        if atr <= 0.0:
            return False
        highs = list(self._high_window)
        lows = list(self._low_window)
        if not highs or not lows:
            return False

        if regime == _TREND_UP:
            rolling_high = max(highs)
            long_stop = rolling_high - self.atr_multiplier * atr
            return mid < long_stop
        if regime == _TREND_DOWN:
            rolling_low = min(lows)
            short_stop = rolling_low + self.atr_multiplier * atr
            return mid > short_stop
        return False

    # --- decision ------------------------------------------------------

    def decide(self, signal: SignalEvent) -> AgentDecisionTrace:
        """Gate *signal* through regime filter, Chandelier Exit, and hold period.

        Returns an :class:`AgentDecisionTrace` (BUY / SELL / HOLD) and
        appends it to the bounded ring buffer.
        """
        rationale: list[str] = []
        direction: str
        confidence: float

        if len(self._mid_window) < self.slow_window:
            direction = _HOLD
            confidence = 0.0
            rationale.append("momentum_neutral")
        else:
            fast = self._fast_sma()
            slow = self._slow_sma()
            regime = self._classify_regime(fast, slow)
            self._last_regime = regime

            mid = list(self._mid_window)[-1]

            if regime in (_RANGE, _VOL_SPIKE):
                direction = _HOLD
                confidence = 0.0
                rationale.append(
                    "regime_range" if regime == _RANGE else "regime_vol_spike"
                )
            elif self._chandelier_stop_violated(regime, mid):
                direction = _HOLD
                confidence = 0.0
                rationale.append("chandelier_stop_violated")
            else:
                # Regime is TREND_UP or TREND_DOWN — gate on signal side.
                if regime == _TREND_UP:
                    rationale.append("momentum_up")
                    if signal.side is Side.BUY:
                        direction = _BUY
                        rationale.append("ma_crossover_buy")
                    else:
                        direction = _HOLD
                        confidence = 0.0
                else:  # TREND_DOWN
                    rationale.append("momentum_down")
                    if signal.side is Side.SELL:
                        direction = _SELL
                        rationale.append("ma_crossover_sell")
                    else:
                        direction = _HOLD
                        confidence = 0.0

                if direction == _HOLD:
                    confidence = 0.0
                else:
                    confidence = float(signal.confidence)

                    # Minimum hold period — prevent rapid directional flip.
                    if (
                        direction != self._last_committed_direction
                        and self._last_committed_direction != _HOLD
                        and self._ticks_since_direction_change < self.min_hold_ticks
                    ):
                        direction = _HOLD
                        confidence = 0.0
                        rationale.append("min_hold_period")

                    if direction != _HOLD and confidence < self.min_confidence:
                        direction = _HOLD
                        confidence = 0.0
                        rationale.append("confidence_below_floor")

        # Track hold-period counter.
        if direction != _HOLD:
            if direction != self._last_committed_direction:
                self._ticks_since_direction_change = 0
            else:
                self._ticks_since_direction_change += 1
            self._last_committed_direction = direction
        else:
            self._ticks_since_direction_change += 1

        trace = AgentDecisionTrace(
            ts_ns=int(signal.ts_ns),
            signal_id=str(signal.meta.get("signal_id", "")),
            direction=direction,
            confidence=confidence,
            rationale_tags=tuple(rationale),
            memory_refs=(),
        )
        self._last_decision_direction = direction
        self._last_decision_confidence = confidence
        self._last_decision_ts_ns = int(signal.ts_ns)
        self._record_decision(trace)
        return trace

    # --- INV-54 introspection -----------------------------------------

    def state_snapshot(self) -> Mapping[str, str]:
        return {
            "agent_id": self.agent_id,
            "lifecycle": "ACTIVE",
            "last_decision_direction": self._last_decision_direction,
            "last_decision_confidence": f"{self._last_decision_confidence:.6f}",
            "last_decision_ts_ns": str(self._last_decision_ts_ns),
            "decisions_in_window": str(len(self._decision_buffer)),
            "fast_window": str(self.fast_window),
            "slow_window": str(self.slow_window),
            "atr_period": str(self.atr_period),
            "atr_multiplier": f"{self.atr_multiplier:.6f}",
            "last_regime": self._last_regime,
            "ticks_since_direction_change": str(self._ticks_since_direction_change),
            "last_committed_direction": self._last_committed_direction,
        }


__all__ = ["SwingTraderAgent"]

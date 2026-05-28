"""AGT-07 — adversarial market observer (7th AGT-XX agent).

This agent does **not** trade. Its sole purpose is to detect patterns
that suggest other market participants are attempting to manipulate
price. When manipulation patterns are detected the agent returns HOLD,
thereby warning the other agents (via the shared signal pipeline) that
market microstructure is currently suspect.

Detected patterns
-----------------

1. **Wash trading** — repeated trades of similar size at nearly
   identical prices within a short window. Detected when the rolling
   standard deviation of mid prices over ``wash_window`` ticks is
   below ``wash_vol_threshold`` *and* the tick count in the window
   exceeds ``wash_min_ticks`` (high activity, near-zero price movement).

2. **Spoofing** — large orders that appear and disappear without
   trading. Proxied here by detecting sudden large spread expansions
   (book depth withdrawn) followed by immediate contraction. Detected
   when the spread expands by more than ``spoof_spread_factor`` × the
   rolling-average spread and then contracts back within
   ``spoof_window`` ticks.

3. **Stop hunting** — a sharp short-lived price spike beyond recent
   range followed by an immediate reversal. Detected when the mid
   price moves more than ``stop_hunt_range_factor`` × ATR outside the
   recent high/low channel and then reverts within ``stop_hunt_window``
   ticks.

The agent emits HOLD whenever any pattern is active. It always
records a trace (for audit), tagging the specific pattern(s) detected.

INV-54 invariants enforced via
:class:`~intelligence_engine.agents._base.AgentBase`:

* :meth:`state_snapshot` is pure (no clock, no PRNG, no IO).
* :meth:`recent_decisions` is O(1) per call (bounded ring buffer).
* ``state_snapshot`` keys subset
  ``registry/agent_state_keys.yaml#AGT-07-adversarial-observer``.
* ``rationale_tags`` drawn from ``registry/agent_rationale_tags.yaml``.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from statistics import stdev

from core.contracts.agent import AgentDecisionTrace, AgentIntrospection
from core.contracts.events import Side, SignalEvent
from core.contracts.market import MarketTick
from intelligence_engine.agents._base import AgentBase

_BUY = "BUY"
_SELL = "SELL"
_HOLD = "HOLD"


@dataclass
class AdversarialObserver(AgentBase, AgentIntrospection):
    """Adversarial market observer (AGT-07).

    Observes market microstructure for manipulation patterns and
    returns HOLD to warn downstream agents when patterns are active.

    Attributes
    ----------
    agent_id:
        Stable INV-54 identifier.
    wash_window:
        Number of ticks over which wash-trading detection is applied.
    wash_vol_threshold:
        Maximum price standard deviation (in price units) over
        ``wash_window`` ticks to classify as wash trading (near-zero
        genuine price movement).
    wash_min_ticks:
        Minimum tick count in ``wash_window`` to trigger wash-trade
        detection (avoid false positives on sparse data).
    spoof_spread_factor:
        Minimum ratio of current spread to rolling-average spread to
        flag a potential spoofing event.
    spoof_window:
        Number of ticks within which the spread must contract back
        after a spoof expansion to confirm spoofing.
    stop_hunt_range_factor:
        Minimum ratio of the mid-price excursion beyond the recent
        high/low channel (measured in ATR units) to flag a stop hunt.
    stop_hunt_window:
        Number of ticks over which the stop-hunt reversal must occur.
    atr_period:
        Rolling period for ATR used in stop-hunt detection.
    ring_capacity:
        Ring buffer capacity for :meth:`recent_decisions`.
    """

    agent_id: str = "AGT-07-adversarial-observer"
    wash_window: int = 20
    wash_vol_threshold: float = 0.0002
    wash_min_ticks: int = 10
    spoof_spread_factor: float = 3.0
    spoof_window: int = 5
    stop_hunt_range_factor: float = 1.5
    stop_hunt_window: int = 8
    atr_period: int = 14
    ring_capacity: int = 64

    # Internal rolling state.
    _mid_window: deque[float] = field(init=False, repr=False)
    _spread_window: deque[float] = field(init=False, repr=False)
    _high_window: deque[float] = field(init=False, repr=False)
    _low_window: deque[float] = field(init=False, repr=False)
    _tr_window: deque[float] = field(init=False, repr=False)
    # Counters tracking ticks since a pattern was first detected.
    _ticks_since_spoof_expansion: int = field(default=-1, init=False, repr=False)
    _ticks_since_stop_hunt: int = field(default=-1, init=False, repr=False)
    _prev_close: float = field(default=0.0, init=False, repr=False)
    # Last detected pattern set for state_snapshot.
    _active_patterns: tuple[str, ...] = field(default=(), init=False, repr=False)
    _last_decision_direction: str = field(default=_HOLD, init=False, repr=False)
    _last_decision_confidence: float = field(default=0.0, init=False, repr=False)
    _last_decision_ts_ns: int = field(default=0, init=False, repr=False)
    _total_alerts: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.wash_window < 2:
            raise ValueError("wash_window must be >= 2")
        if self.wash_vol_threshold < 0.0:
            raise ValueError("wash_vol_threshold must be >= 0")
        if self.wash_min_ticks < 1:
            raise ValueError("wash_min_ticks must be >= 1")
        if self.spoof_spread_factor <= 1.0:
            raise ValueError("spoof_spread_factor must be > 1")
        if self.spoof_window < 1:
            raise ValueError("spoof_window must be >= 1")
        if self.stop_hunt_range_factor <= 0.0:
            raise ValueError("stop_hunt_range_factor must be > 0")
        if self.stop_hunt_window < 1:
            raise ValueError("stop_hunt_window must be >= 1")
        if self.atr_period < 1:
            raise ValueError("atr_period must be >= 1")
        AgentBase.__init__(self, self.agent_id, self.ring_capacity)
        max_window = max(self.wash_window, self.spoof_window, self.stop_hunt_window)
        self._mid_window = deque(maxlen=max_window)
        self._spread_window = deque(maxlen=max_window)
        self._high_window = deque(maxlen=self.atr_period)
        self._low_window = deque(maxlen=self.atr_period)
        self._tr_window = deque(maxlen=self.atr_period)

    # --- inputs --------------------------------------------------------

    def observe_tick(self, tick: MarketTick) -> None:
        """Update rolling buffers from a market tick."""
        if tick.bid <= 0.0 or tick.ask <= 0.0 or tick.ask < tick.bid:
            return
        mid = 0.5 * (tick.bid + tick.ask)
        spread = tick.ask - tick.bid
        if mid <= 0.0:
            return

        high = tick.ask
        low = tick.bid
        close = mid
        prev = self._prev_close if self._prev_close > 0.0 else close
        tr = max(high - low, abs(high - prev), abs(low - prev))

        self._mid_window.append(mid)
        self._spread_window.append(spread)
        self._high_window.append(high)
        self._low_window.append(low)
        self._tr_window.append(tr)
        self._prev_close = close

        # Advance spoof/stop-hunt counters.
        if self._ticks_since_spoof_expansion >= 0:
            self._ticks_since_spoof_expansion += 1
        if self._ticks_since_stop_hunt >= 0:
            self._ticks_since_stop_hunt += 1

    # --- pattern detectors --------------------------------------------

    def _detect_wash_trading(self) -> bool:
        """True when high tick activity with near-zero price movement."""
        mids = list(self._mid_window)
        recent = mids[-self.wash_window :]
        if len(recent) < self.wash_min_ticks:
            return False
        # Use stdev if enough data; fall back to range otherwise.
        if len(recent) >= 2:
            vol = stdev(recent)
        else:
            vol = max(recent) - min(recent)
        return vol < self.wash_vol_threshold

    def _detect_spoofing(self, current_spread: float) -> bool:
        """True when a spread spike appeared and reverted within spoof_window."""
        spreads = list(self._spread_window)
        if len(spreads) < 3:
            return False
        avg_spread = sum(spreads[:-1]) / len(spreads[:-1])
        if avg_spread <= 0.0:
            return False

        # Check for an expansion in the recent past.
        for i, s in enumerate(spreads[-self.spoof_window - 1 : -1]):
            if s > avg_spread * self.spoof_spread_factor:
                # Expansion detected; check if current spread has reverted.
                if current_spread < avg_spread * self.spoof_spread_factor:
                    return True
        return False

    def _detect_stop_hunt(self) -> bool:
        """True when price spiked beyond ATR-based channel and is reverting."""
        mids = list(self._mid_window)
        highs = list(self._high_window)
        lows = list(self._low_window)
        trs = list(self._tr_window)
        if len(mids) < self.stop_hunt_window + 1:
            return False
        if not trs:
            return False

        atr = sum(trs) / len(trs)
        if atr <= 0.0:
            return False

        recent_mids = mids[-self.stop_hunt_window :]
        channel_high = max(highs[: -1]) if len(highs) > 1 else highs[0]
        channel_low = min(lows[: -1]) if len(lows) > 1 else lows[0]
        current_mid = mids[-1]
        peak = max(recent_mids)
        trough = min(recent_mids)

        # Spike up above channel then reverse.
        if peak > channel_high + self.stop_hunt_range_factor * atr:
            if current_mid < channel_high:
                return True
        # Spike down below channel then reverse.
        if trough < channel_low - self.stop_hunt_range_factor * atr:
            if current_mid > channel_low:
                return True
        return False

    # --- decision ------------------------------------------------------

    def decide(self, signal: SignalEvent) -> AgentDecisionTrace:
        """Evaluate patterns and always return HOLD when any is active.

        This agent *never* returns BUY or SELL — it is a pure observer.
        The returned :class:`AgentDecisionTrace` carries the detected
        pattern tags so downstream consumers can log the alert.
        """
        rationale: list[str] = []

        current_spread = (
            list(self._spread_window)[-1] if self._spread_window else 0.0
        )

        # Run all detectors.
        patterns: list[str] = []
        if self._detect_wash_trading():
            patterns.append("adversarial_wash_trade_detected")
        if self._detect_spoofing(current_spread):
            patterns.append("adversarial_spoof_detected")
        if self._detect_stop_hunt():
            patterns.append("adversarial_stop_hunt_detected")

        if patterns:
            rationale.extend(patterns)
            self._active_patterns = tuple(patterns)
            self._total_alerts += 1
        else:
            # No manipulation detected — still HOLD (we never trade).
            rationale.append("adversarial_no_pattern")
            self._active_patterns = ()

        # Always HOLD — this agent does not generate directional intent.
        direction = _HOLD
        confidence = 0.0

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

    @property
    def active_patterns(self) -> tuple[str, ...]:
        """Return the set of pattern tags detected in the last tick.

        Non-empty when any manipulation pattern was active. Downstream
        agents can poll this without consuming a decision slot.
        """
        return self._active_patterns

    @property
    def manipulation_suspected(self) -> bool:
        """True when at least one manipulation pattern is currently active."""
        return len(self._active_patterns) > 0

    # --- INV-54 introspection -----------------------------------------

    def state_snapshot(self) -> Mapping[str, str]:
        return {
            "agent_id": self.agent_id,
            "lifecycle": "ACTIVE",
            "last_decision_direction": self._last_decision_direction,
            "last_decision_confidence": f"{self._last_decision_confidence:.6f}",
            "last_decision_ts_ns": str(self._last_decision_ts_ns),
            "decisions_in_window": str(len(self._decision_buffer)),
            "active_patterns": ",".join(self._active_patterns),
            "manipulation_suspected": str(self.manipulation_suspected),
            "total_alerts": str(self._total_alerts),
        }


__all__ = ["AdversarialObserver"]

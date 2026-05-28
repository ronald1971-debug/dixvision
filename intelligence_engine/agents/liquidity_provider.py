"""AGT-06 — market-making / liquidity provision agent.

Simulates a simplified liquidity-provision strategy that manages:

1. **Bid-ask spread estimation** — tracks a rolling mid-price EMA
   and an average observed spread (``ask - bid``) from ticks. The
   agent skips decisions when the observed spread is below the target
   spread.

2. **Fair value estimation** — uses a rolling EMA of the mid price
   as the "fair value" reference. Quotes are posted symmetrically
   around fair value at the target spread.

3. **Inventory skew** — when the agent's simulated net inventory
   (accumulated BUY minus SELL) drifts beyond ``max_inventory``, it
   skews quotes toward the reducing direction (more aggressive on the
   side that reduces inventory) until re-centred. The skew factor
   adjusts effective confidence.

Because the LP agent generates both BUY and SELL orders (it wants to
be on both sides of the book), the ``decide()`` method examines
whether the upstream signal is asking for a BUY or SELL fill and
responds with the appropriate quote direction, modulated by inventory
skew. When inventory is at the maximum absolute level on the same side
as the signal, the agent emits HOLD to stop accumulating.

INV-54 invariants enforced via
:class:`~intelligence_engine.agents._base.AgentBase`:

* :meth:`state_snapshot` is pure (no clock, no PRNG, no IO).
* :meth:`recent_decisions` is O(1) per call (bounded ring buffer).
* ``state_snapshot`` keys subset
  ``registry/agent_state_keys.yaml#AGT-06-lp``.
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

_EMA_ALPHA_DEFAULT = 2.0 / (20 + 1)  # 20-tick EMA


def _ema_update(prev: float, new_value: float, alpha: float) -> float:
    """Exponential moving average single-step update."""
    if prev == 0.0:
        return new_value
    return alpha * new_value + (1.0 - alpha) * prev


@dataclass
class LiquidityProviderAgent(AgentBase, AgentIntrospection):
    """Market-making / liquidity provision agent (AGT-06).

    Attributes
    ----------
    agent_id:
        Stable INV-54 identifier.
    target_spread_bps:
        Desired quoted spread in basis points. The agent will not quote
        when the market spread is already below this threshold (no
        profitable edge).
    max_inventory:
        Maximum allowed absolute net inventory (normalised, unitless).
        Inventory is tracked as ``+1`` per BUY decision and ``-1`` per
        SELL decision. When ``|inventory| >= max_inventory`` in the
        direction of the new signal, the agent emits HOLD.
    inventory_skew_factor:
        Fraction by which confidence is boosted on the inventory-
        reducing side and penalised on the inventory-accumulating side.
        ``confidence_adjusted = confidence * (1 ± inventory_skew_factor
        * |inventory| / max_inventory)``. Clamped to [0, 1].
    ema_alpha:
        Smoothing factor for the fair-value EMA. Default: 20-tick EMA.
    min_confidence:
        Confidence floor below which a directional decision is
        downgraded to HOLD.
    ring_capacity:
        Ring buffer capacity for :meth:`recent_decisions`.
    """

    agent_id: str = "AGT-06-lp"
    target_spread_bps: float = 10.0
    max_inventory: float = 1.0
    inventory_skew_factor: float = 0.5
    ema_alpha: float = _EMA_ALPHA_DEFAULT
    min_confidence: float = 0.05
    ring_capacity: int = 64

    _fair_value_ema: float = field(default=0.0, init=False, repr=False)
    _spread_ema: float = field(default=0.0, init=False, repr=False)
    _net_inventory: float = field(default=0.0, init=False, repr=False)
    _tick_count: int = field(default=0, init=False, repr=False)
    _last_bid: float = field(default=0.0, init=False, repr=False)
    _last_ask: float = field(default=0.0, init=False, repr=False)
    _last_decision_direction: str = field(default=_HOLD, init=False, repr=False)
    _last_decision_confidence: float = field(default=0.0, init=False, repr=False)
    _last_decision_ts_ns: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.target_spread_bps < 0.0:
            raise ValueError("target_spread_bps must be >= 0")
        if not (self.max_inventory > 0.0):
            raise ValueError("max_inventory must be > 0")
        if not 0.0 <= self.inventory_skew_factor <= 1.0:
            raise ValueError("inventory_skew_factor must be in [0, 1]")
        if not 0.0 < self.ema_alpha <= 1.0:
            raise ValueError("ema_alpha must be in (0, 1]")
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("min_confidence must be in [0, 1]")
        AgentBase.__init__(self, self.agent_id, self.ring_capacity)

    # --- inputs --------------------------------------------------------

    def observe_tick(self, tick: MarketTick) -> None:
        """Update fair-value EMA and observed spread EMA from a tick."""
        if tick.bid <= 0.0 or tick.ask <= 0.0 or tick.ask < tick.bid:
            return
        mid = 0.5 * (tick.bid + tick.ask)
        spread = tick.ask - tick.bid

        self._fair_value_ema = _ema_update(self._fair_value_ema, mid, self.ema_alpha)
        self._spread_ema = _ema_update(self._spread_ema, spread, self.ema_alpha)
        self._last_bid = tick.bid
        self._last_ask = tick.ask
        self._tick_count += 1

    # --- internals -----------------------------------------------------

    def _inventory_skew(self, intended_direction: str) -> float:
        """Return a confidence multiplier in [0, 2] based on inventory skew.

        * Reducing direction (opposite of current inventory lean) → boost.
        * Accumulating direction (same as current inventory lean) → penalty.
        * Zero inventory → no skew (multiplier = 1.0).
        """
        if self.max_inventory <= 0.0:
            return 1.0
        skew_ratio = self._net_inventory / self.max_inventory  # in [-1, 1]
        # Positive inventory → we are long → prefer SELL to reduce.
        if intended_direction == _SELL:
            # Reducing direction: boost confidence when long.
            return 1.0 + self.inventory_skew_factor * abs(skew_ratio)
        elif intended_direction == _BUY:
            # Accumulating direction when already long: penalise.
            return 1.0 - self.inventory_skew_factor * abs(skew_ratio)
        return 1.0

    def _inventory_at_limit(self, intended_direction: str) -> bool:
        """Return True if inventory is maxed out in the intended direction."""
        if intended_direction == _BUY and self._net_inventory >= self.max_inventory:
            return True
        if intended_direction == _SELL and self._net_inventory <= -self.max_inventory:
            return True
        return False

    # --- decision ------------------------------------------------------

    def decide(self, signal: SignalEvent) -> AgentDecisionTrace:
        """Generate a liquidity-provision decision for *signal*.

        Returns an :class:`AgentDecisionTrace` (BUY / SELL / HOLD) and
        appends it to the bounded ring buffer.
        """
        rationale: list[str] = []
        direction: str
        confidence: float

        # Not enough data yet.
        if self._tick_count == 0 or self._fair_value_ema <= 0.0:
            direction = _HOLD
            confidence = 0.0
            rationale.append("momentum_neutral")
        else:
            # Spread profitability check: only quote if market spread is
            # wide enough relative to target.
            if self._last_ask > 0.0 and self._fair_value_ema > 0.0:
                market_spread_bps = (
                    (self._last_ask - self._last_bid) / self._fair_value_ema * 10_000.0
                )
            else:
                market_spread_bps = 0.0

            if market_spread_bps < self.target_spread_bps:
                direction = _HOLD
                confidence = 0.0
                rationale.append("spread_too_tight")
            else:
                # Use signal side as intended quote direction.
                if signal.side is Side.BUY:
                    intended = _BUY
                elif signal.side is Side.SELL:
                    intended = _SELL
                else:
                    intended = _HOLD

                if intended == _HOLD:
                    direction = _HOLD
                    confidence = 0.0
                    rationale.append("momentum_neutral")
                elif self._inventory_at_limit(intended):
                    direction = _HOLD
                    confidence = 0.0
                    rationale.append("inventory_limit")
                else:
                    direction = intended
                    skew = self._inventory_skew(intended)
                    confidence = float(signal.confidence) * skew
                    confidence = max(0.0, min(1.0, confidence))

                    if intended == _BUY:
                        rationale.append("lp_quote_buy")
                    else:
                        rationale.append("lp_quote_sell")

                    if confidence < self.min_confidence:
                        direction = _HOLD
                        confidence = 0.0
                        rationale.append("confidence_below_floor")

        # Update simulated inventory on active decisions.
        if direction == _BUY:
            self._net_inventory = min(
                self._net_inventory + 1.0, self.max_inventory * 2.0
            )
        elif direction == _SELL:
            self._net_inventory = max(
                self._net_inventory - 1.0, -self.max_inventory * 2.0
            )

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
            "fair_value_ema": f"{self._fair_value_ema:.6f}",
            "spread_ema": f"{self._spread_ema:.6f}",
            "net_inventory": f"{self._net_inventory:.6f}",
            "target_spread_bps": f"{self.target_spread_bps:.6f}",
            "max_inventory": f"{self.max_inventory:.6f}",
            "tick_count": str(self._tick_count),
        }


__all__ = ["LiquidityProviderAgent"]

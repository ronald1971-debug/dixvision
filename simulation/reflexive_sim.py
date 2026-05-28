"""Reflexive simulation engine (BUILD-DIRECTIVE — Tier 4.1).

Implements Soros-style reflexive market simulation where:
- Agent actions AFFECT market prices (feedback loops)
- Market moves AFFECT agent beliefs (perception update)
- Both loops create self-reinforcing or self-correcting dynamics

This goes beyond standard backtesting by modeling the
market-as-agent interaction (second-order effects).

Key concepts:
- Reflexivity coefficient: how much agent action moves price
- Belief update rate: how fast agents adapt to new prices
- Stability threshold: point where feedback becomes unstable
- Bubble detection: identifying runaway reflexive loops
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ReflexiveRegime(StrEnum):
    """Market regime based on reflexive dynamics."""

    EQUILIBRIUM = "EQUILIBRIUM"  # price ≈ fundamental
    POSITIVE_FEEDBACK = "POSITIVE_FEEDBACK"  # bubble forming
    NEGATIVE_FEEDBACK = "NEGATIVE_FEEDBACK"  # mean-reverting
    UNSTABLE = "UNSTABLE"  # runaway / crash imminent
    CRISIS = "CRISIS"  # post-bubble collapse


@dataclass(slots=True)
class MarketState:
    """Current state of the reflexive market."""

    price: float
    fundamental_value: float
    sentiment: float  # -1.0 to 1.0
    reflexivity_coefficient: float  # how much actions move price
    belief_divergence: float  # gap between belief and reality
    feedback_strength: float  # current feedback loop intensity
    regime: ReflexiveRegime
    ts_ns: int


@dataclass(slots=True)
class AgentBelief:
    """An agent's belief about market state."""

    agent_id: str
    expected_price: float
    confidence: float
    bias: float  # -1 (bearish) to 1 (bullish)
    position_size: float
    update_rate: float  # how fast beliefs adapt


@dataclass(frozen=True, slots=True)
class SimulationStep:
    """A single step in the reflexive simulation."""

    step_id: int
    price_before: float
    price_after: float
    fundamental_value: float
    net_demand: float
    feedback_delta: float
    regime: ReflexiveRegime
    bubble_risk: float  # 0-1
    ts_ns: int


class ReflexiveSimEngine:
    """Reflexive market simulation engine.

    Models the two-way interaction between agent beliefs/actions
    and market prices. Produces emergent phenomena:
    - Bubbles (self-reinforcing positive feedback)
    - Crashes (sudden regime shift)
    - Mean reversion (negative feedback dominance)
    - Regime transitions
    """

    def __init__(
        self,
        *,
        initial_price: float = 100.0,
        fundamental_value: float = 100.0,
        reflexivity_coefficient: float = 0.1,
        mean_reversion_strength: float = 0.02,
        noise_scale: float = 0.01,
        bubble_threshold: float = 0.3,
    ) -> None:
        self._price = initial_price
        self._fundamental = fundamental_value
        self._reflexivity = reflexivity_coefficient
        self._mean_reversion = mean_reversion_strength
        self._noise_scale = noise_scale
        self._bubble_threshold = bubble_threshold
        self._agents: dict[str, AgentBelief] = {}
        self._history: list[SimulationStep] = []
        self._step_count = 0

    def add_agent(self, agent: AgentBelief) -> None:
        """Add an agent to the simulation."""
        self._agents[agent.agent_id] = agent

    def step(self, *, ts_ns: int = 0, external_shock: float = 0.0) -> SimulationStep:
        """Advance simulation by one step.

        Process:
        1. Agents form demands based on beliefs
        2. Net demand moves price (reflexivity)
        3. New price updates agent beliefs
        4. Check for regime transitions
        """
        price_before = self._price

        # 1. Calculate net demand from all agents
        net_demand = 0.0
        for agent in self._agents.values():
            # Agent buys if expected_price > current, sells if lower
            expected_return = (agent.expected_price - self._price) / self._price
            agent_demand = expected_return * agent.confidence * agent.position_size
            net_demand += agent_demand * agent.bias

        # 2. Price impact (reflexivity)
        feedback_delta = net_demand * self._reflexivity

        # 3. Mean reversion toward fundamental
        reversion = (self._fundamental - self._price) * self._mean_reversion

        # 4. External shock
        self._price += feedback_delta + reversion + external_shock

        # 5. Update agent beliefs (second-order effect)
        price_change = (self._price - price_before) / max(price_before, 0.001)
        for agent in self._agents.values():
            # Agents update expected price based on recent movement
            agent.expected_price += (self._price - agent.expected_price) * agent.update_rate
            # Confidence increases when correct, decreases when wrong
            was_correct = (agent.bias > 0 and price_change > 0) or (
                agent.bias < 0 and price_change < 0
            )
            if was_correct:
                agent.confidence = min(1.0, agent.confidence * 1.02)
            else:
                agent.confidence = max(0.1, agent.confidence * 0.97)

        # 6. Detect regime
        divergence = abs(self._price - self._fundamental) / self._fundamental
        feedback_intensity = abs(feedback_delta) / max(self._price * 0.01, 0.001)
        regime = self._classify_regime(divergence, feedback_intensity)
        bubble_risk = min(1.0, divergence / self._bubble_threshold)

        self._step_count += 1
        step = SimulationStep(
            step_id=self._step_count,
            price_before=price_before,
            price_after=self._price,
            fundamental_value=self._fundamental,
            net_demand=net_demand,
            feedback_delta=feedback_delta,
            regime=regime,
            bubble_risk=bubble_risk,
            ts_ns=ts_ns,
        )
        self._history.append(step)
        return step

    def run(self, *, steps: int, ts_start: int = 0, ts_step: int = 1000) -> list[SimulationStep]:
        """Run simulation for N steps."""
        results: list[SimulationStep] = []
        for i in range(steps):
            result = self.step(ts_ns=ts_start + i * ts_step)
            results.append(result)
        return results

    @property
    def current_state(self) -> MarketState:
        """Get current market state."""
        divergence = abs(self._price - self._fundamental) / self._fundamental
        sentiment = sum(a.bias * a.confidence for a in self._agents.values()) / max(
            len(self._agents), 1
        )
        return MarketState(
            price=self._price,
            fundamental_value=self._fundamental,
            sentiment=sentiment,
            reflexivity_coefficient=self._reflexivity,
            belief_divergence=divergence,
            feedback_strength=abs(self._history[-1].feedback_delta) if self._history else 0.0,
            regime=self._classify_regime(divergence, 0.0),
            ts_ns=self._history[-1].ts_ns if self._history else 0,
        )

    @property
    def history(self) -> list[SimulationStep]:
        """Get simulation history."""
        return list(self._history)

    def _classify_regime(self, divergence: float, feedback_intensity: float) -> ReflexiveRegime:
        """Classify current regime based on dynamics."""
        if divergence < 0.05:
            return ReflexiveRegime.EQUILIBRIUM
        if divergence > 0.5:
            return ReflexiveRegime.CRISIS
        if divergence > self._bubble_threshold:
            return ReflexiveRegime.UNSTABLE
        if feedback_intensity > 0.1:
            return ReflexiveRegime.POSITIVE_FEEDBACK
        return ReflexiveRegime.NEGATIVE_FEEDBACK

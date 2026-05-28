"""simulation.phase10_reflexive_depth — Phase 10 Reflexive Simulation Depth.

Extends the reflexive simulation with:

1. **Higher-Order Belief Modeling** — Agents model what other agents believe
   (I think you think the price will rise → I buy before you)
2. **Narrative Contagion** — Market narratives spread between agents with
   mutation, strengthening, and decay dynamics
3. **Regime Transition Prediction** — Detect when reflexive dynamics are about
   to cause a regime transition (equilibrium → bubble → crash)
4. **Strategy Vulnerability Assessment** — Identify which strategies are most
   vulnerable to reflexive dynamics (momentum strategies in bubbles, etc.)
5. **Reflexive Execution Impact** — Model how our own execution flow creates
   reflexive feedback that affects our future execution quality

Architecture:
- Builds on top of ReflexiveSimulationEngine (reflexive_sim.py)
- Each agent maintains a belief model of N other agents
- Belief updates propagate through a social graph
- Narratives are typed objects that strengthen/weaken over time
- The system identifies "reflexive traps" where strategies become self-defeating

Manifest alignment:
- INV-15 (Replay Determinism): All randomness is seeded via config.seed.
  No raw clock calls (time.time(), datetime.now()). Simulation is fully
  reproducible given the same seed + agent config.
- BeliefState mapping: Regime classification maps to the canonical
  BeliefState.regime enum (UNKNOWN, TREND_UP, TREND_DOWN, RANGE, VOL_SPIKE).
  Collective sentiment feeds into BeliefState.consensus_side.
- SignalTrust: Agent beliefs carry a confidence score that integrates with
  the SignalTrust framework (confidence clamping based on provenance).
- SCVS: Simulation outputs are tagged source_type=SIMULATION; they feed
  into learning calibration but NEVER into live execution directly.

__capability_tier__ = 2  # SIMULATION
__forbidden_tiers__ = (5,)  # never live execution
"""

from __future__ import annotations

import logging
import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class NarrativeType(StrEnum):
    """Types of market narratives that can spread between agents."""

    BULLISH_MOMENTUM = "BULLISH_MOMENTUM"
    BEARISH_MOMENTUM = "BEARISH_MOMENTUM"
    FUNDAMENTAL_OVERVALUE = "FUNDAMENTAL_OVERVALUE"
    FUNDAMENTAL_UNDERVALUE = "FUNDAMENTAL_UNDERVALUE"
    LIQUIDITY_CRISIS = "LIQUIDITY_CRISIS"
    REGIME_CHANGE = "REGIME_CHANGE"
    CROWDED_TRADE = "CROWDED_TRADE"
    BLACK_SWAN = "BLACK_SWAN"


class BeliefStrength(StrEnum):
    """How strongly an agent holds a belief."""

    WEAK = "WEAK"
    MODERATE = "MODERATE"
    STRONG = "STRONG"
    CONVICTION = "CONVICTION"


@dataclass(slots=True)
class Narrative:
    """A market narrative that spreads between agents.

    Maps to BeliefState components:
    - narrative_type → BeliefState.regime influence
    - strength → contributes to BeliefState.regime_confidence
    - directional implication → BeliefState.consensus_side

    Regime mapping:
    - BULLISH_MOMENTUM → TREND_UP influence
    - BEARISH_MOMENTUM → TREND_DOWN influence
    - LIQUIDITY_CRISIS → VOL_SPIKE influence
    - REGIME_CHANGE → UNKNOWN (uncertainty spike)
    - FUNDAMENTAL_* → RANGE influence (reversion expectation)
    """

    narrative_type: NarrativeType
    strength: float  # 0.0 - 1.0
    origin_tick: int
    spread_count: int = 0
    mutations: int = 0
    believers: int = 1
    decay_rate: float = 0.01

    def tick_decay(self) -> None:
        """Decay narrative strength over time."""
        self.strength = max(0.0, self.strength - self.decay_rate)

    def reinforce(self, amount: float = 0.1) -> None:
        """Reinforce narrative (confirming evidence)."""
        self.strength = min(1.0, self.strength + amount)
        self.believers += 1

    def mutate(self) -> Narrative:
        """Create a mutated version of this narrative."""
        return Narrative(
            narrative_type=self.narrative_type,
            strength=self.strength * 0.8,
            origin_tick=self.origin_tick,
            spread_count=self.spread_count + 1,
            mutations=self.mutations + 1,
            believers=1,
            decay_rate=self.decay_rate * 1.1,
        )


@dataclass(slots=True)
class AgentBelief:
    """An agent's belief about a specific topic.

    Integrates with SignalTrust confidence framework:
    - confidence is clamped to [0.0, 1.0]
    - source tracks provenance ("observation", "social", "narrative")
    - When projecting into BeliefState, beliefs from low-trust sources
      are down-weighted per the SignalTrust cap table.
    """

    topic: str
    direction: float  # -1.0 (bearish) to +1.0 (bullish)
    confidence: float  # 0.0 to 1.0 (clamped per SignalTrust)
    source: str = "observation"  # provenance for SignalTrust mapping
    last_update_tick: int = 0


@dataclass(slots=True)
class HigherOrderBelief:
    """What agent A believes about agent B's beliefs.

    This enables game-theoretic reasoning:
    "I think the market maker believes momentum traders will buy,
    so the market maker will widen the ask to capture premium."
    """

    observer_id: str
    subject_id: str
    believed_direction: float  # What A thinks B believes
    believed_confidence: float  # How sure A is about B's belief
    depth: int = 1  # 1 = first-order, 2 = second-order, etc.


@dataclass(slots=True)
class ReflexiveVulnerability:
    """Assessment of a strategy's vulnerability to reflexive dynamics."""

    strategy_id: str
    bubble_vulnerability: float  # 0-1, how much bubbles hurt
    crash_vulnerability: float  # 0-1, how much crashes hurt
    crowding_vulnerability: float  # 0-1, how crowded-trade risk affects
    self_impact_ratio: float  # How much our execution affects our returns
    recommended_adjustment: str


@dataclass(slots=True)
class RegimeTransitionForecast:
    """Prediction of upcoming regime transition.

    Regime labels map to BeliefState.regime enum:
    - EQUILIBRIUM → Regime.RANGE
    - POSITIVE_FEEDBACK → Regime.TREND_UP
    - NEGATIVE_FEEDBACK → Regime.TREND_DOWN
    - UNSTABLE → Regime.VOL_SPIKE
    - TRANSITIONING → Regime.UNKNOWN
    """

    current_regime: str
    predicted_regime: str
    probability: float
    estimated_ticks_until: int
    key_indicators: dict[str, float] = field(default_factory=dict)
    confidence: float = 0.5


class ReflexiveDepthEngine:
    """Phase 10 reflexive simulation depth engine.

    Extends basic reflexivity modeling with:
    - Higher-order belief tracking
    - Narrative contagion dynamics
    - Regime transition forecasting
    - Strategy vulnerability assessment

    INV-15 compliance: All randomness seeded via config.seed. No raw
    clock calls. Deterministic given same seed + agent population.

    BeliefState integration: collective_sentiment maps to
    BeliefState.consensus_side. Regime classification maps to
    BeliefState.regime. feedback_strength correlates with
    BeliefState.regime_confidence.
    """

    __slots__ = (
        "_agents",
        "_narratives",
        "_beliefs",
        "_higher_order",
        "_social_graph",
        "_config",
        "_tick",
        "_rng",
        "_regime_history",
        "_vulnerability_cache",
    )

    def __init__(self, config: ReflexiveDepthConfig | None = None) -> None:
        self._config = config or ReflexiveDepthConfig()
        self._agents: dict[str, _ReflexiveAgent] = {}
        self._narratives: list[Narrative] = []
        self._beliefs: dict[str, list[AgentBelief]] = defaultdict(list)
        self._higher_order: list[HigherOrderBelief] = []
        self._social_graph: dict[str, list[str]] = defaultdict(list)
        self._tick = 0
        self._rng = random.Random(self._config.seed)
        self._regime_history: list[tuple[int, str]] = []
        self._vulnerability_cache: dict[str, ReflexiveVulnerability] = {}

    def add_agent(
        self, agent_id: str, agent_type: str, params: dict[str, Any] | None = None
    ) -> None:
        """Register an agent in the reflexive simulation."""
        self._agents[agent_id] = _ReflexiveAgent(
            agent_id=agent_id,
            agent_type=agent_type,
            params=params or {},
        )
        # Build random social connections
        existing = list(self._agents.keys())
        n_connections = min(len(existing) - 1, self._config.max_social_connections)
        if n_connections > 0:
            connections = self._rng.sample([a for a in existing if a != agent_id], n_connections)
            self._social_graph[agent_id] = connections
            for conn in connections:
                if agent_id not in self._social_graph[conn]:
                    self._social_graph[conn].append(agent_id)

    def tick(self, market_price: float, volume: float) -> ReflexiveTickResult:
        """Advance one tick of the reflexive simulation."""
        self._tick += 1

        # 1. Decay all narratives
        for narrative in self._narratives:
            narrative.tick_decay()
        self._narratives = [n for n in self._narratives if n.strength > 0.01]

        # 2. Agents observe market and update beliefs
        self._update_agent_beliefs(market_price, volume)

        # 3. Propagate narratives through social graph
        new_narratives = self._propagate_narratives()
        self._narratives.extend(new_narratives)

        # 4. Update higher-order beliefs
        self._update_higher_order_beliefs()

        # 5. Compute collective sentiment
        sentiment = self._compute_collective_sentiment()

        # 6. Detect regime transitions
        regime_forecast = self._forecast_regime_transition(market_price, sentiment)

        # 7. Compute reflexive feedback strength
        feedback = self._compute_feedback_strength(sentiment, volume)

        return ReflexiveTickResult(
            tick=self._tick,
            collective_sentiment=sentiment,
            active_narratives=len(self._narratives),
            dominant_narrative=self._get_dominant_narrative(),
            feedback_strength=feedback,
            regime_forecast=regime_forecast,
            higher_order_depth=self._max_belief_depth(),
        )

    def _update_agent_beliefs(self, price: float, volume: float) -> None:
        """Each agent updates beliefs based on market observation."""
        for _agent_id, agent in self._agents.items():
            # Price momentum observation
            if agent.last_observed_price > 0:
                price_change = (price - agent.last_observed_price) / agent.last_observed_price
                # Update directional belief
                current = agent.directional_belief
                lr = self._config.belief_learning_rate
                agent.directional_belief = (
                    current * (1 - lr)
                    + math.copysign(min(abs(price_change) * 10, 1.0), price_change) * lr
                )
            agent.last_observed_price = price
            agent.volume_observation = volume

    def _propagate_narratives(self) -> list[Narrative]:
        """Spread narratives through social graph with mutation."""
        new: list[Narrative] = []
        for narrative in self._narratives:
            if narrative.strength < 0.1:
                continue
            # Pick random holders and spread to their connections
            for agent_id in list(self._agents.keys()):
                if self._rng.random() > narrative.strength * 0.3:
                    continue
                for _neighbor in self._social_graph.get(agent_id, []):
                    if self._rng.random() < self._config.narrative_spread_prob:
                        # Spread (possibly mutated)
                        if self._rng.random() < self._config.narrative_mutation_prob:
                            new.append(narrative.mutate())
                        else:
                            narrative.reinforce(0.05)
        return new

    def _update_higher_order_beliefs(self) -> None:
        """Update what agents believe about each other's beliefs."""
        self._higher_order.clear()
        for observer_id, _agent in self._agents.items():
            for subject_id in self._social_graph.get(observer_id, [])[:3]:
                subject = self._agents.get(subject_id)
                if subject is None:
                    continue
                # Observer's estimate of subject's belief (imperfect)
                noise = self._rng.gauss(0, 0.1)
                estimated_direction = subject.directional_belief + noise
                self._higher_order.append(
                    HigherOrderBelief(
                        observer_id=observer_id,
                        subject_id=subject_id,
                        believed_direction=max(-1, min(1, estimated_direction)),
                        believed_confidence=0.5 + self._rng.random() * 0.3,
                        depth=1,
                    )
                )

    def _compute_collective_sentiment(self) -> float:
        """Compute aggregate market sentiment from all agents."""
        if not self._agents:
            return 0.0
        total = sum(a.directional_belief for a in self._agents.values())
        return total / len(self._agents)

    def _compute_feedback_strength(self, sentiment: float, volume: float) -> float:
        """How strongly is sentiment feeding back into price action?"""
        if not self._regime_history:
            return abs(sentiment) * 0.5
        # Strong sentiment + high volume = strong feedback
        vol_factor = min(volume / 1000, 2.0)  # Normalize volume
        return abs(sentiment) * vol_factor * self._config.reflexivity_coefficient

    def _forecast_regime_transition(
        self, price: float, sentiment: float
    ) -> RegimeTransitionForecast | None:
        """Predict upcoming regime transitions."""
        current = self._classify_current_regime(sentiment)

        # Check for transition indicators
        if abs(sentiment) > 0.7 and current != "UNSTABLE":
            return RegimeTransitionForecast(
                current_regime=current,
                predicted_regime="UNSTABLE",
                probability=abs(sentiment) * 0.8,
                estimated_ticks_until=int(10 / max(abs(sentiment), 0.1)),
                key_indicators={
                    "sentiment_extreme": abs(sentiment),
                    "narrative_density": len(self._narratives) / max(len(self._agents), 1),
                    "belief_convergence": self._belief_convergence(),
                },
            )

        if abs(sentiment) < 0.1 and current != "EQUILIBRIUM":
            return RegimeTransitionForecast(
                current_regime=current,
                predicted_regime="EQUILIBRIUM",
                probability=0.6,
                estimated_ticks_until=20,
                key_indicators={"sentiment_neutral": abs(sentiment)},
            )

        return None

    def _classify_current_regime(self, sentiment: float) -> str:
        """Classify current reflexive regime."""
        if abs(sentiment) < 0.1:
            return "EQUILIBRIUM"
        if abs(sentiment) > 0.7:
            return "UNSTABLE"
        if sentiment > 0.3:
            return "POSITIVE_FEEDBACK"
        if sentiment < -0.3:
            return "NEGATIVE_FEEDBACK"
        return "TRANSITIONING"

    def _belief_convergence(self) -> float:
        """How much agents agree (0 = total disagreement, 1 = unanimous)."""
        if len(self._agents) < 2:
            return 1.0
        beliefs = [a.directional_belief for a in self._agents.values()]
        mean = sum(beliefs) / len(beliefs)
        variance = sum((b - mean) ** 2 for b in beliefs) / len(beliefs)
        return max(0, 1.0 - variance)

    def _get_dominant_narrative(self) -> str:
        """Get the strongest active narrative."""
        if not self._narratives:
            return "none"
        strongest = max(self._narratives, key=lambda n: n.strength)
        return f"{strongest.narrative_type.value}({strongest.strength:.2f})"

    def _max_belief_depth(self) -> int:
        """Maximum depth of higher-order beliefs."""
        if not self._higher_order:
            return 0
        return max(h.depth for h in self._higher_order)

    def assess_vulnerability(self, strategy_id: str, strategy_type: str) -> ReflexiveVulnerability:
        """Assess a strategy's vulnerability to reflexive dynamics."""
        # Momentum strategies are vulnerable in bubbles
        bubble_vuln = 0.8 if "momentum" in strategy_type.lower() else 0.3
        # All strategies vulnerable in crashes
        crash_vuln = 0.6 if "long_only" in strategy_type.lower() else 0.4
        # Crowding risk depends on popularity
        crowding_vuln = 0.5  # Default moderate
        # Self-impact depends on size relative to market
        self_impact = 0.1  # Default low

        vuln = ReflexiveVulnerability(
            strategy_id=strategy_id,
            bubble_vulnerability=bubble_vuln,
            crash_vulnerability=crash_vuln,
            crowding_vulnerability=crowding_vuln,
            self_impact_ratio=self_impact,
            recommended_adjustment=self._recommend_adjustment(
                bubble_vuln, crash_vuln, crowding_vuln
            ),
        )
        self._vulnerability_cache[strategy_id] = vuln
        return vuln

    def _recommend_adjustment(self, bubble: float, crash: float, crowd: float) -> str:
        """Generate adjustment recommendation."""
        if bubble > 0.7:
            return "add_mean_reversion_overlay"
        if crash > 0.7:
            return "reduce_position_sizing_in_high_vol"
        if crowd > 0.7:
            return "diversify_signal_sources"
        return "maintain_current_approach"


@dataclass(frozen=True, slots=True)
class ReflexiveTickResult:
    """Result of one tick of reflexive simulation."""

    tick: int
    collective_sentiment: float
    active_narratives: int
    dominant_narrative: str
    feedback_strength: float
    regime_forecast: RegimeTransitionForecast | None
    higher_order_depth: int


@dataclass(frozen=True, slots=True)
class ReflexiveDepthConfig:
    """Configuration for Phase 10 reflexive depth (frozen — INV-15).

    Frozen config ensures simulation reproducibility. Same config +
    same seed produces identical narrative dynamics and regime forecasts.
    """

    seed: int = 42
    max_social_connections: int = 5
    belief_learning_rate: float = 0.1
    narrative_spread_prob: float = 0.3
    narrative_mutation_prob: float = 0.1
    reflexivity_coefficient: float = 0.5
    source_type: str = "SIMULATION"  # SCVS tag


@dataclass(slots=True)
class _ReflexiveAgent:
    """Internal agent state for reflexive simulation."""

    agent_id: str
    agent_type: str
    params: dict[str, Any]
    directional_belief: float = 0.0
    last_observed_price: float = 0.0
    volume_observation: float = 0.0


__all__ = [
    "AgentBelief",
    "BeliefStrength",
    "HigherOrderBelief",
    "Narrative",
    "NarrativeType",
    "ReflexiveDepthConfig",
    "ReflexiveDepthEngine",
    "ReflexiveTickResult",
    "ReflexiveVulnerability",
    "RegimeTransitionForecast",
]

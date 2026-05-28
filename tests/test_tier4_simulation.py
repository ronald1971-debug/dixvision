"""Tests for Tier 4 simulation depth."""

from simulation.phase10_scenario_engine import (
    Phase10ScenarioEngine,
    ScenarioConfig,
    ScenarioType,
)
from simulation.reflexive_sim import (
    AgentBelief,
    ReflexiveSimEngine,
)


def test_reflexive_sim_equilibrium():
    engine = ReflexiveSimEngine(
        initial_price=100.0,
        fundamental_value=100.0,
        reflexivity_coefficient=0.1,
    )
    # Add balanced agents
    engine.add_agent(
        AgentBelief(
            agent_id="bull",
            expected_price=102.0,
            confidence=0.5,
            bias=0.5,
            position_size=1.0,
            update_rate=0.1,
        )
    )
    engine.add_agent(
        AgentBelief(
            agent_id="bear",
            expected_price=98.0,
            confidence=0.5,
            bias=-0.5,
            position_size=1.0,
            update_rate=0.1,
        )
    )

    results = engine.run(steps=10)
    assert len(results) == 10
    # Price should stay near 100 with balanced agents
    final_price = results[-1].price_after
    assert 95 < final_price < 105


def test_reflexive_sim_bubble():
    engine = ReflexiveSimEngine(
        initial_price=100.0,
        fundamental_value=100.0,
        reflexivity_coefficient=0.5,  # strong reflexivity
        mean_reversion_strength=0.001,  # weak reversion
    )
    # All bullish agents → positive feedback
    for i in range(5):
        engine.add_agent(
            AgentBelief(
                agent_id=f"bull_{i}",
                expected_price=120.0,
                confidence=0.8,
                bias=0.8,
                position_size=2.0,
                update_rate=0.2,
            )
        )

    results = engine.run(steps=200)
    # With strong positive feedback, price should rise above fundamental
    max_price = max(r.price_after for r in results)
    assert max_price > 101.0  # moved above fundamental
    # Verify positive feedback occurred (net demand pushed price)
    positive_steps = sum(1 for r in results if r.feedback_delta > 0)
    assert positive_steps > len(results) * 0.3  # mostly positive feedback


def test_phase10_flash_crash():
    engine = Phase10ScenarioEngine(deterministic_seed=42)
    config = ScenarioConfig(
        scenario_type=ScenarioType.FLASH_CRASH,
        duration_ns=100_000_000,
        initial_price=50000.0,
        volatility=0.02,
        liquidity_depth=1000.0,
        num_agents=10,
        seed=42,
    )
    result = engine.run_scenario(config)
    assert result.total_steps == 100
    assert result.max_drawdown > 0.01  # should have significant drawdown
    assert len(result.price_path) == 101  # initial + 100 steps


def test_phase10_memecoin_pump_dump():
    engine = Phase10ScenarioEngine()
    config = ScenarioConfig(
        scenario_type=ScenarioType.MEMECOIN_PUMP_DUMP,
        duration_ns=60_000_000,
        initial_price=0.001,
        volatility=0.1,
        liquidity_depth=10.0,
        num_agents=5,
        seed=123,
    )
    result = engine.run_scenario(config)
    assert result.total_steps == 60
    # Pump then dump: max rally should be significant
    assert result.max_rally > 0.1


def test_phase10_halving_cycle():
    engine = Phase10ScenarioEngine()
    config = ScenarioConfig(
        scenario_type=ScenarioType.HALVING_CYCLE,
        duration_ns=365_000_000,
        initial_price=30000.0,
        volatility=0.01,
        liquidity_depth=5000.0,
        num_agents=20,
        seed=7,
    )
    result = engine.run_scenario(config)
    assert result.total_steps == 365
    # Halving cycle should produce net positive movement
    final_price = result.price_path[-1]
    assert final_price > config.initial_price

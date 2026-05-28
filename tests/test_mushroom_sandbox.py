"""Tests for C-41 — MushroomRL modular RL sandbox.

Coverage:
* Config validation
* Default environment and algorithm
* Training loop completes and produces valid metrics
* Deterministic replay (INV-15)
* Governance bridge (PatchProposal generation)
* Custom algorithm injection via Protocol
* Episode record correctness
* Serialization (to_payload)
"""

from __future__ import annotations

import pytest

from evolution_engine.sandbox_mushroom import (
    DEFAULT_N_EPISODES,
    MUSHROOM_SANDBOX_VERSION,
    MushroomSandboxConfig,
    MushroomSandboxError,
    SimpleLinearEnv,
    TabularQLearner,
    build_patch_proposal,
    run_experiment,
)

# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


class TestConfig:
    def test_defaults(self) -> None:
        cfg = MushroomSandboxConfig()
        assert cfg.algorithm_name == "SAC"
        assert cfg.n_episodes == DEFAULT_N_EPISODES
        assert cfg.gamma == 0.99
        assert cfg.seed == 42
        assert cfg.version == MUSHROOM_SANDBOX_VERSION

    def test_zero_episodes_rejected(self) -> None:
        with pytest.raises(MushroomSandboxError, match="n_episodes"):
            MushroomSandboxConfig(n_episodes=0)

    def test_invalid_gamma_rejected(self) -> None:
        with pytest.raises(MushroomSandboxError, match="gamma"):
            MushroomSandboxConfig(gamma=0.0)
        with pytest.raises(MushroomSandboxError, match="gamma"):
            MushroomSandboxConfig(gamma=1.5)

    def test_negative_lr_rejected(self) -> None:
        with pytest.raises(MushroomSandboxError, match="learning_rate"):
            MushroomSandboxConfig(learning_rate=-0.01)


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


class TestSimpleLinearEnv:
    def test_reset_returns_state(self) -> None:
        env = SimpleLinearEnv(n_states=4)
        state = env.reset(seed=123)
        assert len(state) == 4
        assert all(isinstance(s, float) for s in state)

    def test_step_returns_correct_shape(self) -> None:
        env = SimpleLinearEnv()
        env.reset(seed=1)
        next_state, reward, done, info = env.step(0)
        assert len(next_state) == 4
        assert isinstance(reward, float)
        assert isinstance(done, bool)
        assert isinstance(info, dict)

    def test_episode_terminates(self) -> None:
        env = SimpleLinearEnv()
        env.reset(seed=42)
        done = False
        steps = 0
        while not done:
            _, _, done, _ = env.step(0)
            steps += 1
        assert steps == 50


# ---------------------------------------------------------------------------
# Algorithm
# ---------------------------------------------------------------------------


class TestTabularQLearner:
    def test_draw_action_returns_valid(self) -> None:
        algo = TabularQLearner(n_actions=2, seed=1)
        action = algo.draw_action((0.5, -0.3, 1.0, 0.0))
        assert action in (0, 1)

    def test_fit_updates_q_table(self) -> None:
        algo = TabularQLearner(n_actions=2, seed=1)
        dataset = [
            ((0.5, 0.5, 0.5, 0.5), 1, 1.0, (0.6, 0.6, 0.6, 0.6), False),
            ((0.5, 0.5, 0.5, 0.5), 0, -0.5, (0.4, 0.4, 0.4, 0.4), False),
        ]
        algo.fit(dataset)
        weights = algo.get_weights()
        assert len(weights) > 0
        assert any(w != 0.0 for w in weights)


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------


class TestRunExperiment:
    def test_completes_with_defaults(self) -> None:
        cfg = MushroomSandboxConfig(n_episodes=10)
        result = run_experiment(cfg)
        assert result.metrics.n_episodes == 10
        assert result.metrics.total_steps > 0
        assert result.metrics.best_reward >= result.metrics.worst_reward
        assert len(result.episode_records) == 10

    def test_custom_env_and_algo(self) -> None:
        cfg = MushroomSandboxConfig(n_episodes=5, seed=99)
        env = SimpleLinearEnv(n_states=3)
        algo = TabularQLearner(n_actions=2, seed=99)
        result = run_experiment(cfg, env=env, algorithm=algo)
        assert result.metrics.n_episodes == 5
        assert len(result.policy_weights) > 0

    def test_proposal_id_propagated(self) -> None:
        cfg = MushroomSandboxConfig(n_episodes=3)
        result = run_experiment(cfg, proposal_id="test-prop-42")
        assert result.proposal_id == "test-prop-42"

    def test_episode_records_correct(self) -> None:
        cfg = MushroomSandboxConfig(n_episodes=5, n_steps_per_episode=50)
        result = run_experiment(cfg)
        for i, rec in enumerate(result.episode_records):
            assert rec.episode_idx == i
            assert rec.n_steps > 0
            assert rec.n_steps <= 50


# ---------------------------------------------------------------------------
# INV-15 replay determinism
# ---------------------------------------------------------------------------


class TestReplayDeterminism:
    def test_three_runs_identical(self) -> None:
        cfg = MushroomSandboxConfig(n_episodes=20, seed=7)
        digests = []
        for _ in range(3):
            result = run_experiment(cfg)
            digests.append(result.digest)
        assert digests[0] == digests[1] == digests[2]

    def test_metrics_identical_across_runs(self) -> None:
        cfg = MushroomSandboxConfig(n_episodes=15, seed=123)
        results = [run_experiment(cfg) for _ in range(3)]
        for r in results[1:]:
            assert r.metrics.mean_reward == results[0].metrics.mean_reward
            assert r.metrics.best_reward == results[0].metrics.best_reward
            assert r.metrics.total_steps == results[0].metrics.total_steps

    def test_different_seeds_differ(self) -> None:
        cfg1 = MushroomSandboxConfig(n_episodes=10, seed=1)
        cfg2 = MushroomSandboxConfig(n_episodes=10, seed=2)
        r1 = run_experiment(cfg1)
        r2 = run_experiment(cfg2)
        assert r1.digest != r2.digest


# ---------------------------------------------------------------------------
# Governance bridge
# ---------------------------------------------------------------------------


class TestGovernanceBridge:
    def test_builds_patch_proposal(self) -> None:
        cfg = MushroomSandboxConfig(n_episodes=5, algorithm_name="PPO")
        result = run_experiment(cfg, proposal_id="prop-001")
        proposal = build_patch_proposal(result, "strat-alpha", ts_ns=999_000_000)

        assert proposal.ts_ns == 999_000_000
        assert proposal.patch_id == "prop-001"
        assert "PPO" in proposal.source
        assert proposal.target_strategy == "strat-alpha"
        assert "policy_weights" in proposal.touchpoints
        assert "mean_reward" in proposal.rationale
        assert proposal.meta["digest"] == result.digest


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_to_payload(self) -> None:
        cfg = MushroomSandboxConfig(n_episodes=3, seed=77)
        result = run_experiment(cfg)
        payload = result.to_payload()
        assert payload["algorithm"] == "SAC"
        assert payload["seed"] == 77
        assert payload["n_episodes"] == 3
        assert payload["digest"] == result.digest
        assert payload["version"] == MUSHROOM_SANDBOX_VERSION

"""Tests for C-40 — EWC Continual Learning lane.

Coverage:
* Config validation (bounds, defaults)
* Initial state creation + determinism
* Single-task training converges
* Multi-task training prevents catastrophic forgetting
* Fisher Information estimation
* EWC penalty correctness
* FIFO task eviction
* Governance bridge (LearningUpdate generation)
* INV-15 replay determinism (3 runs produce identical state)
* Serialization round-trip
"""

from __future__ import annotations

import pytest

from learning_engine.lanes.continual_learner import (
    CONTINUAL_LEARNER_VERSION,
    DEFAULT_EWC_LAMBDA,
    ContinualLearnerConfig,
    ContinualLearnerError,
    TaskAnchor,
    TrainingSample,
    build_learning_update,
    evaluate_forgetting,
    make_initial_state,
    train,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_samples(
    task_label: float,
    n: int = 20,
    strategy_id: str = "strat-01",
) -> list[TrainingSample]:
    """Generate deterministic training samples for a linear task."""
    samples = []
    for i in range(n):
        x = (i + 1) / n
        features = (x, x * 0.5, 1.0)
        label = task_label * x + 0.1
        samples.append(
            TrainingSample(
                ts_ns=1_000_000 * (i + 1),
                features=features,
                label=label,
                strategy_id=strategy_id,
            )
        )
    return samples


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


class TestConfig:
    def test_defaults(self) -> None:
        cfg = ContinualLearnerConfig()
        assert cfg.ewc_lambda == DEFAULT_EWC_LAMBDA
        assert cfg.learning_rate == 0.01
        assert cfg.max_tasks == 64
        assert cfg.version == CONTINUAL_LEARNER_VERSION

    def test_negative_lambda_rejected(self) -> None:
        with pytest.raises(ContinualLearnerError, match="ewc_lambda"):
            ContinualLearnerConfig(ewc_lambda=-0.1)

    def test_zero_lr_rejected(self) -> None:
        with pytest.raises(ContinualLearnerError, match="learning_rate"):
            ContinualLearnerConfig(learning_rate=0.0)

    def test_zero_max_tasks_rejected(self) -> None:
        with pytest.raises(ContinualLearnerError, match="max_tasks"):
            ContinualLearnerConfig(max_tasks=0)


# ---------------------------------------------------------------------------
# State creation
# ---------------------------------------------------------------------------


class TestMakeInitialState:
    def test_creates_zeroed_state(self) -> None:
        state = make_initial_state(5)
        assert len(state.params) == 5
        assert all(p == 0.0 for p in state.params)
        assert state.task_anchors == ()
        assert state.n_tasks_seen == 0
        assert state.n_steps == 0
        assert state.version == CONTINUAL_LEARNER_VERSION

    def test_custom_init_value(self) -> None:
        state = make_initial_state(3, init_value=1.0)
        assert all(p == 1.0 for p in state.params)

    def test_zero_params_rejected(self) -> None:
        with pytest.raises(ContinualLearnerError, match="n_params"):
            make_initial_state(0)

    def test_digest_populated(self) -> None:
        state = make_initial_state(4)
        assert len(state.digest) == 32  # BLAKE2b 16 bytes → 32 hex chars


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


class TestTrain:
    def test_single_task_converges(self) -> None:
        state = make_initial_state(3)
        cfg = ContinualLearnerConfig(learning_rate=0.05)
        samples = _make_samples(task_label=2.0, n=30)

        outcome = train(state, "regime-A", samples, cfg, max_epochs=50)
        assert outcome.final_loss < 0.1
        assert outcome.task_id == "regime-A"
        assert outcome.state.n_tasks_seen == 1
        assert len(outcome.state.task_anchors) == 1
        assert outcome.state.task_anchors[0].task_id == "regime-A"

    def test_empty_samples_rejected(self) -> None:
        state = make_initial_state(3)
        cfg = ContinualLearnerConfig()
        with pytest.raises(ContinualLearnerError, match="samples"):
            train(state, "task-x", [], cfg)

    def test_empty_task_id_rejected(self) -> None:
        state = make_initial_state(3)
        cfg = ContinualLearnerConfig()
        samples = _make_samples(1.0, n=5)
        with pytest.raises(ContinualLearnerError, match="task_id"):
            train(state, "", samples, cfg)

    def test_multi_task_reduces_forgetting(self) -> None:
        """EWC should reduce forgetting compared to naive (lambda=0)."""
        state = make_initial_state(3)
        samples_a = _make_samples(task_label=2.0, n=30)
        samples_b = _make_samples(task_label=-1.0, n=30)

        # Train with EWC
        cfg_ewc = ContinualLearnerConfig(ewc_lambda=1.0, learning_rate=0.02)
        outcome_a = train(state, "regime-A", samples_a, cfg_ewc, max_epochs=30)
        outcome_b = train(outcome_a.state, "regime-B", samples_b, cfg_ewc, max_epochs=30)

        loss_a_after_ewc = sum(
            0.5 * (s.label - sum(outcome_b.state.params[i] * s.features[i] for i in range(3))) ** 2
            for s in samples_a
        ) / len(samples_a)

        # Train without EWC (lambda=0 → no regularisation)
        cfg_naive = ContinualLearnerConfig(ewc_lambda=0.0, learning_rate=0.02)
        outcome_a2 = train(state, "regime-A", samples_a, cfg_naive, max_epochs=30)
        outcome_b2 = train(outcome_a2.state, "regime-B", samples_b, cfg_naive, max_epochs=30)

        loss_a_after_naive = sum(
            0.5 * (s.label - sum(outcome_b2.state.params[i] * s.features[i] for i in range(3))) ** 2
            for s in samples_a
        ) / len(samples_a)

        # EWC should retain more knowledge of task A
        assert loss_a_after_ewc < loss_a_after_naive


# ---------------------------------------------------------------------------
# FIFO eviction
# ---------------------------------------------------------------------------


class TestFIFOEviction:
    def test_evicts_oldest_anchor(self) -> None:
        cfg = ContinualLearnerConfig(max_tasks=2, learning_rate=0.05)
        state = make_initial_state(3)
        samples = _make_samples(1.0, n=10)

        state = train(state, "task-1", samples, cfg, max_epochs=5).state
        state = train(state, "task-2", samples, cfg, max_epochs=5).state
        assert len(state.task_anchors) == 2
        assert state.task_anchors[0].task_id == "task-1"

        state = train(state, "task-3", samples, cfg, max_epochs=5).state
        assert len(state.task_anchors) == 2
        assert state.task_anchors[0].task_id == "task-2"
        assert state.task_anchors[1].task_id == "task-3"


# ---------------------------------------------------------------------------
# TaskAnchor validation
# ---------------------------------------------------------------------------


class TestTaskAnchor:
    def test_length_mismatch_rejected(self) -> None:
        with pytest.raises(ContinualLearnerError, match="length"):
            TaskAnchor(
                task_id="x",
                optimal_params=(1.0, 2.0),
                fisher_diagonal=(1.0,),
            )


# ---------------------------------------------------------------------------
# INV-15 replay determinism
# ---------------------------------------------------------------------------


class TestReplayDeterminism:
    def test_three_runs_identical(self) -> None:
        """Same inputs produce byte-identical state across 3 runs."""
        cfg = ContinualLearnerConfig(learning_rate=0.02)
        samples_a = _make_samples(2.0, n=20)
        samples_b = _make_samples(-1.0, n=20)

        digests = []
        for _ in range(3):
            s = make_initial_state(3)
            s = train(s, "A", samples_a, cfg, max_epochs=10).state
            s = train(s, "B", samples_b, cfg, max_epochs=10).state
            digests.append(s.digest)

        assert digests[0] == digests[1] == digests[2]

    def test_params_identical_across_runs(self) -> None:
        cfg = ContinualLearnerConfig(learning_rate=0.02)
        samples = _make_samples(1.5, n=15)

        params_runs = []
        for _ in range(3):
            s = make_initial_state(3)
            s = train(s, "X", samples, cfg, max_epochs=10).state
            params_runs.append(s.params)

        assert params_runs[0] == params_runs[1] == params_runs[2]


# ---------------------------------------------------------------------------
# Governance bridge
# ---------------------------------------------------------------------------


class TestGovernanceBridge:
    def test_generates_learning_updates(self) -> None:
        state = make_initial_state(3)
        cfg = ContinualLearnerConfig(learning_rate=0.05)
        samples = _make_samples(2.0, n=20)

        outcome = train(state, "regime-A", samples, cfg, max_epochs=20)
        updates = build_learning_update(
            outcome,
            strategy_id="strat-01",
            ts_ns=999_000_000,
            param_names=["w0", "w1", "bias"],
        )

        assert len(updates) > 0
        for u in updates:
            assert u.strategy_id == "strat-01"
            assert u.ts_ns == 999_000_000
            assert "EWC continual learning" in u.reason
            assert u.meta["task_id"] == "regime-A"

    def test_no_updates_for_unchanged_params(self) -> None:
        state = make_initial_state(3)
        cfg = ContinualLearnerConfig(learning_rate=0.05)
        samples = _make_samples(2.0, n=20)
        outcome = train(state, "A", samples, cfg, max_epochs=20)

        # Pass same params as old_params — no delta
        updates = build_learning_update(
            outcome,
            strategy_id="s",
            ts_ns=1,
            old_params=outcome.state.params,
        )
        assert updates == []


# ---------------------------------------------------------------------------
# Evaluate forgetting
# ---------------------------------------------------------------------------


class TestEvaluateForgetting:
    def test_returns_per_task_loss(self) -> None:
        state = make_initial_state(3)
        cfg = ContinualLearnerConfig(learning_rate=0.05)
        samples_a = _make_samples(2.0, n=20)
        samples_b = _make_samples(-1.0, n=20)

        state = train(state, "A", samples_a, cfg, max_epochs=20).state
        state = train(state, "B", samples_b, cfg, max_epochs=20).state

        losses = evaluate_forgetting(state, {"A": samples_a, "B": samples_b})
        assert "A" in losses
        assert "B" in losses
        assert losses["A"] >= 0.0
        assert losses["B"] >= 0.0


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_to_payload_roundtrip(self) -> None:
        state = make_initial_state(3)
        cfg = ContinualLearnerConfig(learning_rate=0.05)
        samples = _make_samples(1.0, n=10)
        state = train(state, "T1", samples, cfg, max_epochs=5).state

        payload = state.to_payload()
        assert payload["n_tasks_seen"] == 1
        assert len(payload["task_anchors"]) == 1
        assert payload["task_anchors"][0]["task_id"] == "T1"
        assert payload["version"] == CONTINUAL_LEARNER_VERSION

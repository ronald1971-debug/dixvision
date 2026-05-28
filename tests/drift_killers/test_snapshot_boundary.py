"""Drift killer — snapshot boundary invariant.

Verifies that dataclasses used as state snapshots are:
  1. Frozen (immutable)
  2. Slotted (no __dict__)
  3. Hashable (can be stored in sets / used as dict keys)
"""

from __future__ import annotations

import dataclasses

import pytest


_SNAPSHOT_CLASSES = [
    ("execution_engine.strategic_execution.market_impact.model", "ImpactEstimate"),
    ("execution_engine.strategic_execution.market_impact.depth_estimator", "DepthSnapshot"),
    ("execution_engine.strategic_execution.market_impact.slippage_curve", "SlippagePoint"),
    ("execution_engine.strategic_execution.optimal_execution", "ExecutionSlice"),
    ("execution_engine.strategic_execution.optimal_execution", "OptimalExecutionPlan"),
    ("execution_engine.strategic_execution.adversarial_executor", "AdversarialPlan"),
    ("sensory.web_autolearn.trader_intelligence.profile_extractor", "TraderProfile"),
    ("sensory.web_autolearn.trader_intelligence.performance_validator", "PerformanceClaim"),
    ("sensory.web_autolearn.trader_intelligence.performance_validator", "ValidationResult"),
]


def _import(module: str, cls_name: str) -> type:
    import importlib  # noqa: PLC0415
    mod = importlib.import_module(module)
    return getattr(mod, cls_name)


class TestSnapshotBoundary:
    @pytest.mark.parametrize("module,cls_name", _SNAPSHOT_CLASSES)
    def test_is_frozen_dataclass(self, module: str, cls_name: str) -> None:
        cls = _import(module, cls_name)
        assert dataclasses.is_dataclass(cls), f"{cls_name} is not a dataclass"
        params = cls.__dataclass_params__  # type: ignore[attr-defined]
        assert params.frozen, f"{cls_name} dataclass is not frozen"

    @pytest.mark.parametrize("module,cls_name", _SNAPSHOT_CLASSES)
    def test_is_slotted(self, module: str, cls_name: str) -> None:
        cls = _import(module, cls_name)
        assert hasattr(cls, "__slots__"), f"{cls_name} does not use __slots__"

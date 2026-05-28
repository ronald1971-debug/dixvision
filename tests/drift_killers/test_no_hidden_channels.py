"""Drift killer — no hidden communication channels.

Verifies that pure-computation modules do not import the event bus,
fast lane, hazard lane, or offline lane at module level (B1 constraint).
These modules must be side-effect free at import time.
"""

from __future__ import annotations

import importlib
import sys

import pytest

_PURE_MODULES = [
    "execution_engine.strategic_execution.market_impact.model",
    "execution_engine.strategic_execution.market_impact.depth_estimator",
    "execution_engine.strategic_execution.market_impact.slippage_curve",
    "execution_engine.strategic_execution.optimal_execution",
    "execution_engine.strategic_execution.adversarial_executor",
    "intelligence_engine.cross_asset.correlation_matrix",
    "intelligence_engine.cross_asset.lead_lag",
    "intelligence_engine.cross_asset.contagion_detector",
    "intelligence_engine.cross_asset.basket_constructor",
    "intelligence_engine.opponent_model.behavior_predictor",
    "intelligence_engine.opponent_model.crowd_density",
    "intelligence_engine.macro.regime_classifier",
    "intelligence_engine.macro.hidden_state_detector",
    "intelligence_engine.macro.latent_embedder",
    "sensory.web_autolearn.trader_intelligence.profile_extractor",
    "sensory.web_autolearn.trader_intelligence.behavior_analyzer",
    "sensory.web_autolearn.trader_intelligence.performance_validator",
]

_FORBIDDEN_IMPORTS = frozenset({
    "execution.async_bus",
    "execution.fast_lane",
    "execution.hazard_lane",
    "execution.offline_lane",
    "execution.event_emitter",
})


class TestNoHiddenChannels:
    @pytest.mark.parametrize("module_name", _PURE_MODULES)
    def test_module_does_not_import_bus(self, module_name: str) -> None:
        before = set(sys.modules.keys())
        try:
            importlib.import_module(module_name)
        except ImportError:
            pytest.skip(f"Module {module_name!r} not importable (optional dep missing)")

        new_modules = set(sys.modules.keys()) - before
        violations = new_modules & _FORBIDDEN_IMPORTS
        assert not violations, (
            f"Pure module {module_name!r} imported bus modules at load time: {violations}"
        )

    @pytest.mark.parametrize("module_name", _PURE_MODULES)
    def test_module_has_no_wallclock(self, module_name: str) -> None:
        try:
            mod = importlib.import_module(module_name)
        except ImportError:
            pytest.skip(f"Module {module_name!r} not importable")
        import inspect  # noqa: PLC0415
        try:
            src = inspect.getsource(mod)
        except (OSError, TypeError):
            pytest.skip("Cannot read source")
        # time.time() or datetime.now() in a pure module violates INV-15
        forbidden_calls = ["time.time()", "datetime.now()", "time.monotonic()"]
        for call in forbidden_calls:
            assert call not in src, (
                f"Pure module {module_name!r} contains wall-clock call {call!r}"
            )

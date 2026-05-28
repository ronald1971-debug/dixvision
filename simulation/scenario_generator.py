"""simulation/scenario_generator.py
DIX VISION v42.2 — Scenario Generator

Generates structured market scenarios for backtesting and strategy
evaluation. Scenarios can be parametric (generated from distribution
parameters) or historical (sampled from ledger data).

Pure functions + frozen dataclasses (INV-15 replay determinism).
All randomness is seeded deterministically from scenario_id.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ScenarioKind(StrEnum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE_BOUND = "RANGE_BOUND"
    VOLATILITY_SPIKE = "VOLATILITY_SPIKE"
    FLASH_CRASH = "FLASH_CRASH"
    RECOVERY = "RECOVERY"
    REGIME_SHIFT = "REGIME_SHIFT"


@dataclass(frozen=True, slots=True)
class ScenarioConfig:
    """Parameters for scenario generation."""
    scenario_id: str
    kind: ScenarioKind
    num_bars: int = 500
    initial_price: float = 100.0
    base_volatility: float = 0.01
    drift: float = 0.0
    trend_strength: float = 0.0
    crash_magnitude: float = 0.0
    recovery_speed: float = 0.5


@dataclass(frozen=True, slots=True)
class OHLCVBar:
    """One OHLCV bar."""
    ts_ns: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class Scenario:
    """A generated market scenario."""
    scenario_id: str
    kind: ScenarioKind
    bars: tuple[OHLCVBar, ...]
    metadata: dict[str, str]


def _seeded_rng(scenario_id: str) -> random.Random:
    seed = int(hashlib.md5(scenario_id.encode()).hexdigest()[:8], 16)
    return random.Random(seed)


def generate_scenario(config: ScenarioConfig, bar_interval_ns: int = 60_000_000_000) -> Scenario:
    """Generate a scenario from config. Fully deterministic (INV-15)."""
    rng = _seeded_rng(config.scenario_id)
    bars: list[OHLCVBar] = []
    price = config.initial_price
    ts = 1_700_000_000_000_000_000  # fixed reference epoch

    for i in range(config.num_bars):
        vol = config.base_volatility
        drift = config.drift

        if config.kind == ScenarioKind.TREND_UP:
            drift = abs(config.trend_strength) * 0.001
        elif config.kind == ScenarioKind.TREND_DOWN:
            drift = -abs(config.trend_strength) * 0.001
        elif config.kind == ScenarioKind.VOLATILITY_SPIKE:
            if i == config.num_bars // 2:
                vol *= 5.0
        elif config.kind == ScenarioKind.FLASH_CRASH:
            if i == config.num_bars // 3:
                drift = -config.crash_magnitude
            elif i > config.num_bars // 3 and i < config.num_bars // 3 + 20:
                drift = config.crash_magnitude * config.recovery_speed * 0.05

        ret = drift + vol * rng.gauss(0, 1)
        close = max(price * (1.0 + ret), 0.01)
        high = close * (1.0 + abs(rng.gauss(0, vol * 0.5)))
        low = close * (1.0 - abs(rng.gauss(0, vol * 0.5)))
        low = min(low, min(price, close))
        high = max(high, max(price, close))
        volume = abs(rng.gauss(1000, 300))

        bars.append(OHLCVBar(
            ts_ns=ts + i * bar_interval_ns,
            open=price,
            high=high,
            low=low,
            close=close,
            volume=volume,
        ))
        price = close

    return Scenario(
        scenario_id=config.scenario_id,
        kind=config.kind,
        bars=tuple(bars),
        metadata={
            "num_bars": str(config.num_bars),
            "initial_price": str(config.initial_price),
            "kind": config.kind.value,
        },
    )


def generate_scenario_set(
    base_id: str,
    kinds: list[ScenarioKind] | None = None,
    num_bars: int = 500,
) -> list[Scenario]:
    """Generate one scenario per kind."""
    if kinds is None:
        kinds = list(ScenarioKind)
    scenarios: list[Scenario] = []
    for kind in kinds:
        cfg = ScenarioConfig(
            scenario_id=f"{base_id}_{kind.value}",
            kind=kind,
            num_bars=num_bars,
        )
        scenarios.append(generate_scenario(cfg))
    return scenarios


__all__ = [
    "OHLCVBar",
    "Scenario",
    "ScenarioConfig",
    "ScenarioKind",
    "generate_scenario",
    "generate_scenario_set",
]

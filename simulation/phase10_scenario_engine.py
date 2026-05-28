"""Phase 10 scenario engine (BUILD-DIRECTIVE — Tier 4.1).

Generates complete trading scenarios combining:
- Market microstructure (LOB, spreads, fills)
- Macro events (rate decisions, CPI, NFP)
- Crypto-specific events (halving, depegs, hacks)
- Multi-agent interaction (reflexive dynamics)
- Regime transitions (trending → crisis → recovery)

Produces deterministic scenario replays for testing strategy
robustness across diverse market conditions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ScenarioType(StrEnum):
    """Pre-built scenario archetypes."""

    FLASH_CRASH = "flash_crash"
    GRADUAL_TREND = "gradual_trend"
    RANGE_BOUND = "range_bound"
    LIQUIDITY_CRISIS = "liquidity_crisis"
    EXCHANGE_OUTAGE = "exchange_outage"
    BLACK_SWAN = "black_swan"
    HALVING_CYCLE = "halving_cycle"
    STABLECOIN_DEPEG = "stablecoin_depeg"
    REGULATORY_SHOCK = "regulatory_shock"
    MEV_ATTACK = "mev_attack"
    WHALE_MANIPULATION = "whale_manipulation"
    MEMECOIN_PUMP_DUMP = "memecoin_pump_dump"


@dataclass(frozen=True, slots=True)
class ScenarioEvent:
    """An event within a scenario."""

    ts_ns: int
    event_type: str
    magnitude: float  # -1.0 to 1.0 (negative = bearish)
    duration_ns: int
    affected_symbols: tuple[str, ...]
    metadata: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ScenarioConfig:
    """Configuration for a scenario run."""

    scenario_type: ScenarioType
    duration_ns: int
    initial_price: float
    volatility: float
    liquidity_depth: float
    num_agents: int
    seed: int  # deterministic seed


@dataclass(slots=True)
class ScenarioResult:
    """Result of running a scenario."""

    config: ScenarioConfig
    events: list[ScenarioEvent] = field(default_factory=list)
    price_path: list[float] = field(default_factory=list)
    regime_changes: list[tuple[int, str]] = field(default_factory=list)
    max_drawdown: float = 0.0
    max_rally: float = 0.0
    total_steps: int = 0


class Phase10ScenarioEngine:
    """Generates and runs complete trading scenarios.

    Combines multiple simulation components into coherent
    multi-hour/multi-day scenarios for strategy stress testing.
    """

    def __init__(self, *, deterministic_seed: int = 42) -> None:
        self._seed = deterministic_seed
        self._scenarios: dict[str, ScenarioResult] = {}

    def generate_scenario(self, config: ScenarioConfig) -> list[ScenarioEvent]:
        """Generate events for a scenario type."""
        generators = {
            ScenarioType.FLASH_CRASH: self._gen_flash_crash,
            ScenarioType.GRADUAL_TREND: self._gen_gradual_trend,
            ScenarioType.RANGE_BOUND: self._gen_range_bound,
            ScenarioType.LIQUIDITY_CRISIS: self._gen_liquidity_crisis,
            ScenarioType.BLACK_SWAN: self._gen_black_swan,
            ScenarioType.HALVING_CYCLE: self._gen_halving_cycle,
            ScenarioType.STABLECOIN_DEPEG: self._gen_stablecoin_depeg,
            ScenarioType.MEMECOIN_PUMP_DUMP: self._gen_memecoin_pump_dump,
        }
        gen = generators.get(config.scenario_type, self._gen_range_bound)
        return gen(config)

    def run_scenario(self, config: ScenarioConfig) -> ScenarioResult:
        """Run a complete scenario and return results."""
        events = self.generate_scenario(config)
        result = ScenarioResult(config=config, events=events)

        price = config.initial_price
        max_price = price
        min_price = price
        result.price_path.append(price)

        for event in events:
            price *= 1 + event.magnitude * config.volatility
            price = max(price, 0.001)  # prevent negative
            result.price_path.append(price)
            max_price = max(max_price, price)
            min_price = min(min_price, price)
            result.total_steps += 1

        if max_price > 0:
            result.max_drawdown = (max_price - min_price) / max_price
        result.max_rally = (max_price - config.initial_price) / config.initial_price

        scenario_id = f"{config.scenario_type}_{config.seed}"
        self._scenarios[scenario_id] = result
        return result

    def _gen_flash_crash(self, config: ScenarioConfig) -> list[ScenarioEvent]:
        """Generate flash crash scenario."""
        events: list[ScenarioEvent] = []
        step_ns = config.duration_ns // 100

        # Build-up phase (60 steps)
        for i in range(60):
            events.append(
                ScenarioEvent(
                    ts_ns=i * step_ns,
                    event_type="normal_trading",
                    magnitude=0.001,
                    duration_ns=step_ns,
                    affected_symbols=("BTC/USDT",),
                )
            )

        # Crash (10 steps)
        for i in range(10):
            events.append(
                ScenarioEvent(
                    ts_ns=(60 + i) * step_ns,
                    event_type="flash_crash",
                    magnitude=-0.5 * (1 - i / 10),  # decreasing severity
                    duration_ns=step_ns,
                    affected_symbols=("BTC/USDT", "ETH/USDT"),
                )
            )

        # Recovery (30 steps)
        for i in range(30):
            events.append(
                ScenarioEvent(
                    ts_ns=(70 + i) * step_ns,
                    event_type="recovery",
                    magnitude=0.02,
                    duration_ns=step_ns,
                    affected_symbols=("BTC/USDT",),
                )
            )

        return events

    def _gen_gradual_trend(self, config: ScenarioConfig) -> list[ScenarioEvent]:
        """Generate gradual trending scenario."""
        events: list[ScenarioEvent] = []
        step_ns = config.duration_ns // 200
        for i in range(200):
            events.append(
                ScenarioEvent(
                    ts_ns=i * step_ns,
                    event_type="trend",
                    magnitude=0.005,
                    duration_ns=step_ns,
                    affected_symbols=("BTC/USDT",),
                )
            )
        return events

    def _gen_range_bound(self, config: ScenarioConfig) -> list[ScenarioEvent]:
        """Generate range-bound scenario."""
        events: list[ScenarioEvent] = []
        step_ns = config.duration_ns // 200
        for i in range(200):
            # Oscillate around zero
            import math

            mag = 0.01 * math.sin(i * 0.1)
            events.append(
                ScenarioEvent(
                    ts_ns=i * step_ns,
                    event_type="range",
                    magnitude=mag,
                    duration_ns=step_ns,
                    affected_symbols=("BTC/USDT",),
                )
            )
        return events

    def _gen_liquidity_crisis(self, config: ScenarioConfig) -> list[ScenarioEvent]:
        """Generate liquidity crisis scenario."""
        events: list[ScenarioEvent] = []
        step_ns = config.duration_ns // 100
        for i in range(100):
            mag = -0.02 if i > 30 and i < 70 else 0.001
            events.append(
                ScenarioEvent(
                    ts_ns=i * step_ns,
                    event_type="liquidity_crisis",
                    magnitude=mag,
                    duration_ns=step_ns,
                    affected_symbols=("BTC/USDT", "ETH/USDT", "SOL/USDT"),
                    metadata={"spread_multiplier": 3.0 if i > 30 else 1.0},
                )
            )
        return events

    def _gen_black_swan(self, config: ScenarioConfig) -> list[ScenarioEvent]:
        """Generate black swan event."""
        events: list[ScenarioEvent] = []
        step_ns = config.duration_ns // 50
        # Sudden massive drop
        for i in range(50):
            if i == 10:
                mag = -0.8
            elif i > 10 and i < 20:
                mag = -0.1
            elif i >= 20:
                mag = 0.03
            else:
                mag = 0.001
            events.append(
                ScenarioEvent(
                    ts_ns=i * step_ns,
                    event_type="black_swan",
                    magnitude=mag,
                    duration_ns=step_ns,
                    affected_symbols=("BTC/USDT", "ETH/USDT", "SOL/USDT"),
                )
            )
        return events

    def _gen_halving_cycle(self, config: ScenarioConfig) -> list[ScenarioEvent]:
        """Generate Bitcoin halving cycle scenario."""
        events: list[ScenarioEvent] = []
        step_ns = config.duration_ns // 365  # ~1 year of daily data
        for i in range(365):
            # Pre-halving accumulation, post-halving rally
            if i < 100:
                mag = 0.002  # slow accumulation
            elif i < 150:
                mag = 0.01  # post-halving rally start
            elif i < 250:
                mag = 0.015  # parabolic
            else:
                mag = -0.01  # distribution
            events.append(
                ScenarioEvent(
                    ts_ns=i * step_ns,
                    event_type="halving_cycle",
                    magnitude=mag,
                    duration_ns=step_ns,
                    affected_symbols=("BTC/USDT",),
                )
            )
        return events

    def _gen_stablecoin_depeg(self, config: ScenarioConfig) -> list[ScenarioEvent]:
        """Generate stablecoin depeg scenario (UST/LUNA style)."""
        events: list[ScenarioEvent] = []
        step_ns = config.duration_ns // 72  # 72 hours
        for i in range(72):
            if i < 12:
                mag = -0.005  # slight wobble
            elif i < 24:
                mag = -0.05  # accelerating depeg
            elif i < 48:
                mag = -0.2  # death spiral
            else:
                mag = -0.01  # aftermath
            events.append(
                ScenarioEvent(
                    ts_ns=i * step_ns,
                    event_type="depeg",
                    magnitude=mag,
                    duration_ns=step_ns,
                    affected_symbols=("USDT/USD", "BTC/USDT"),
                )
            )
        return events

    def _gen_memecoin_pump_dump(self, config: ScenarioConfig) -> list[ScenarioEvent]:
        """Generate memecoin pump & dump scenario."""
        events: list[ScenarioEvent] = []
        step_ns = config.duration_ns // 60  # 60 minutes
        for i in range(60):
            if i < 5:
                mag = 0.5  # insane pump
            elif i < 10:
                mag = 0.2  # continued momentum
            elif i < 15:
                mag = 0.0  # distribution
            elif i < 20:
                mag = -0.3  # dump begins
            elif i < 30:
                mag = -0.5  # rug
            else:
                mag = -0.01  # dead token
            events.append(
                ScenarioEvent(
                    ts_ns=i * step_ns,
                    event_type="pump_dump",
                    magnitude=mag,
                    duration_ns=step_ns,
                    affected_symbols=("MEME/SOL",),
                )
            )
        return events

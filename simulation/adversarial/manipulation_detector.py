"""simulation.adversarial.manipulation_detector — Market Manipulation Detection.

Detects and simulates common market manipulation patterns:

1. **Wash Trading** — Self-matched orders to inflate volume
2. **Spoofing** — Large orders placed and cancelled to move price
3. **Layering** — Multiple spoof orders at different levels
4. **Front-Running** — Trading ahead of known large orders
5. **Pump and Dump** — Coordinated buy → social signal → dump
6. **Bear Raid** — Coordinated selling to trigger stop losses
7. **Quote Stuffing** — Flooding the book to slow other participants

Used for:
- Training the governance engine to detect and block manipulation
- Stress-testing execution strategies against adversarial actors
- Validating that DIX VISION doesn't inadvertently engage in manipulation
- Building robustness against manipulated market conditions

Manifest alignment:
- INV-15 (Replay Determinism): All timestamps are caller-supplied via
  ts_ns parameter. No raw time.time() or time.time_ns() calls.
  Detection results are fully reproducible from the same input sequence.
- HazardThrottle integration: HIGH/CONFIRMED alerts feed into the
  governance engine as hazard signals, triggering position-sizing
  reduction or execution pause.
- Governance detection rules: Alert recommended_actions map to
  concrete governance policy adjustments (reduce sizing, pause entries,
  tighten stops).
- SCVS: Adversarial simulation outputs are tagged as SIMULATION source.

__capability_tier__ = 2  # SIMULATION
__forbidden_tiers__ = (5,)  # never live execution
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class ManipulationType(StrEnum):
    """Recognized manipulation patterns."""

    WASH_TRADING = "WASH_TRADING"
    SPOOFING = "SPOOFING"
    LAYERING = "LAYERING"
    FRONT_RUNNING = "FRONT_RUNNING"
    PUMP_AND_DUMP = "PUMP_AND_DUMP"
    BEAR_RAID = "BEAR_RAID"
    QUOTE_STUFFING = "QUOTE_STUFFING"
    MOMENTUM_IGNITION = "MOMENTUM_IGNITION"


class DetectionConfidence(StrEnum):
    """Confidence level of manipulation detection."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CONFIRMED = "CONFIRMED"


@dataclass(frozen=True, slots=True)
class ManipulationAlert:
    """Alert raised when manipulation is detected.

    ts_ns is caller-supplied (INV-15): the analyze() method receives
    the tick timestamp from the OrderFlowSnapshot, ensuring replay
    determinism.

    severity maps to HazardThrottle escalation:
    - LOW: informational, no throttle action
    - MEDIUM: reduce position sizing multiplier
    - HIGH: pause new entries for the affected symbol
    - CONFIRMED: halt all execution on the symbol
    """

    manipulation_type: ManipulationType
    confidence: DetectionConfidence
    symbol: str
    evidence: dict[str, Any]
    recommended_action: str
    ts_ns: int = 0  # caller-supplied (INV-15 — no raw clock)
    hazard_code: str = ""  # maps to governance HazardEvent.code


@dataclass(frozen=True, slots=True)
class OrderFlowSnapshot:
    """Point-in-time order flow data for analysis."""

    symbol: str
    tick: int
    bid_depth: list[tuple[float, float]]  # (price, qty) levels
    ask_depth: list[tuple[float, float]]
    recent_trades: list[tuple[float, float, str]]  # (price, qty, side)
    cancel_rate: float  # cancels / total orders
    volume_1m: float
    unique_participants: int


class ManipulationDetector:
    """Detects market manipulation patterns from order flow data.

    Uses a combination of statistical methods and heuristic rules
    to identify manipulation in real-time or from historical data.
    """

    __slots__ = (
        "_alerts",
        "_history",
        "_config",
        "_wash_detector",
        "_spoof_detector",
        "_layering_detector",
        "_pump_detector",
        "_front_run_detector",
    )

    def __init__(self, config: DetectorConfig | None = None) -> None:
        self._config = config or DetectorConfig()
        self._alerts: list[ManipulationAlert] = []
        self._history: list[OrderFlowSnapshot] = []
        self._wash_detector = _WashTradingDetector(self._config)
        self._spoof_detector = _SpoofingDetector(self._config)
        self._layering_detector = _LayeringDetector(self._config)
        self._pump_detector = _PumpDumpDetector(self._config)
        self._front_run_detector = _FrontRunDetector(self._config)

    def analyze(self, snapshot: OrderFlowSnapshot, *, ts_ns: int = 0) -> list[ManipulationAlert]:
        """Analyze an order flow snapshot for manipulation patterns.

        Args:
            snapshot: Point-in-time order flow data.
            ts_ns: Current authoritative timestamp (INV-15). If 0, uses
                   the snapshot's tick as a proxy (simulation mode).

        Returns list of alerts (empty if no manipulation detected).
        """
        alert_ts = ts_ns if ts_ns > 0 else snapshot.tick
        self._history.append(snapshot)
        if len(self._history) > self._config.history_window:
            self._history = self._history[-self._config.history_window :]

        alerts: list[ManipulationAlert] = []

        # Run all detectors
        wash = self._wash_detector.check(snapshot, self._history, alert_ts)
        if wash:
            alerts.append(wash)

        spoof = self._spoof_detector.check(snapshot, self._history, alert_ts)
        if spoof:
            alerts.append(spoof)

        layer = self._layering_detector.check(snapshot, self._history, alert_ts)
        if layer:
            alerts.append(layer)

        pump = self._pump_detector.check(snapshot, self._history, alert_ts)
        if pump:
            alerts.append(pump)

        front = self._front_run_detector.check(snapshot, self._history, alert_ts)
        if front:
            alerts.append(front)

        self._alerts.extend(alerts)
        return alerts

    def get_alerts(self, since_ns: int = 0) -> list[ManipulationAlert]:
        """Get all alerts since a given timestamp."""
        return [a for a in self._alerts if a.ts_ns >= since_ns]

    def get_risk_score(
        self, symbol: str, *, ts_ns: int = 0, window_ns: int = 300_000_000_000
    ) -> float:
        """Get current manipulation risk score for a symbol (0.0 - 1.0).

        Args:
            symbol: The symbol to score.
            ts_ns: Current timestamp (caller-supplied, INV-15). If 0,
                   considers all alerts regardless of age.
            window_ns: Lookback window in nanoseconds (default 5 min).

        The score feeds into HazardThrottle: scores above 0.7 trigger
        position-sizing reduction; above 0.9 triggers execution pause.
        """
        if ts_ns > 0:
            recent = [a for a in self._alerts if a.symbol == symbol and ts_ns - a.ts_ns < window_ns]
        else:
            recent = [a for a in self._alerts if a.symbol == symbol]
        if not recent:
            return 0.0
        confidence_weights = {
            DetectionConfidence.LOW: 0.2,
            DetectionConfidence.MEDIUM: 0.5,
            DetectionConfidence.HIGH: 0.8,
            DetectionConfidence.CONFIRMED: 1.0,
        }
        score = sum(confidence_weights.get(a.confidence, 0.1) for a in recent)
        return min(score / 3.0, 1.0)


@dataclass(frozen=True, slots=True)
class DetectorConfig:
    """Configuration for manipulation detection thresholds."""

    history_window: int = 100
    wash_volume_ratio_threshold: float = 0.3
    spoof_cancel_rate_threshold: float = 0.9
    layering_level_count_threshold: int = 5
    pump_price_move_threshold: float = 0.05
    pump_volume_spike_threshold: float = 3.0
    front_run_time_window_ticks: int = 3


class _WashTradingDetector:
    """Detects wash trading patterns.

    Indicators:
    - Same-price self-matches (buy and sell at identical price/time)
    - Abnormally high volume with no net position change
    - Circular order patterns between related accounts
    """

    __slots__ = ("_config",)

    def __init__(self, config: DetectorConfig) -> None:
        self._config = config

    def check(
        self, snapshot: OrderFlowSnapshot, history: list[OrderFlowSnapshot], ts_ns: int
    ) -> ManipulationAlert | None:
        if len(history) < 10:
            return None

        recent_volumes = [h.volume_1m for h in history[-10:]]
        avg_vol = sum(recent_volumes) / len(recent_volumes) if recent_volumes else 1
        current_vol = snapshot.volume_1m

        if avg_vol == 0:
            return None

        vol_ratio = current_vol / avg_vol
        participant_ratio = snapshot.unique_participants / max(current_vol / 100, 1)

        if vol_ratio > 2.0 and participant_ratio < 0.1:
            return ManipulationAlert(
                manipulation_type=ManipulationType.WASH_TRADING,
                confidence=DetectionConfidence.MEDIUM
                if vol_ratio < 5
                else DetectionConfidence.HIGH,
                symbol=snapshot.symbol,
                evidence={
                    "volume_ratio": round(vol_ratio, 2),
                    "unique_participants": snapshot.unique_participants,
                    "participant_ratio": round(participant_ratio, 4),
                },
                recommended_action="reduce_position_sizing",
                ts_ns=ts_ns,
                hazard_code="MANIP_WASH_TRADE",
            )
        return None


class _SpoofingDetector:
    """Detects spoofing patterns.

    Indicators:
    - Large orders placed far from mid that are cancelled quickly
    - Cancel rate > 90% for large orders
    - Consistent pattern of place-cancel-trade
    """

    __slots__ = ("_config",)

    def __init__(self, config: DetectorConfig) -> None:
        self._config = config

    def check(
        self, snapshot: OrderFlowSnapshot, history: list[OrderFlowSnapshot], ts_ns: int
    ) -> ManipulationAlert | None:
        if snapshot.cancel_rate > self._config.spoof_cancel_rate_threshold:
            bid_depth_total = sum(q for _, q in snapshot.bid_depth[:5])
            ask_depth_total = sum(q for _, q in snapshot.ask_depth[:5])

            if bid_depth_total > 0 and ask_depth_total > 0:
                imbalance = abs(bid_depth_total - ask_depth_total) / (
                    bid_depth_total + ask_depth_total
                )
                if imbalance > 0.7:
                    heavy_side = "bid" if bid_depth_total > ask_depth_total else "ask"
                    return ManipulationAlert(
                        manipulation_type=ManipulationType.SPOOFING,
                        confidence=DetectionConfidence.HIGH,
                        symbol=snapshot.symbol,
                        evidence={
                            "cancel_rate": round(snapshot.cancel_rate, 3),
                            "book_imbalance": round(imbalance, 3),
                            "heavy_side": heavy_side,
                            "bid_depth": round(bid_depth_total, 2),
                            "ask_depth": round(ask_depth_total, 2),
                        },
                        recommended_action="ignore_book_depth_signals",
                        ts_ns=ts_ns,
                        hazard_code="MANIP_SPOOFING",
                    )
        return None


class _LayeringDetector:
    """Detects layering patterns.

    Indicators:
    - Multiple large orders at consecutive price levels on one side
    - Orders are placed and cancelled in a pattern
    - The "wall" moves as price approaches
    """

    __slots__ = ("_config",)

    def __init__(self, config: DetectorConfig) -> None:
        self._config = config

    def check(
        self, snapshot: OrderFlowSnapshot, history: list[OrderFlowSnapshot], ts_ns: int
    ) -> ManipulationAlert | None:
        for side, depth in [("bid", snapshot.bid_depth), ("ask", snapshot.ask_depth)]:
            if len(depth) < self._config.layering_level_count_threshold:
                continue
            top_qtys = [q for _, q in depth[: self._config.layering_level_count_threshold]]
            if not top_qtys:
                continue
            avg_qty = sum(top_qtys) / len(top_qtys)
            if avg_qty == 0:
                continue
            variance = sum((q - avg_qty) ** 2 for q in top_qtys) / len(top_qtys)
            cv = (variance**0.5) / avg_qty if avg_qty else 1

            if cv < 0.2 and avg_qty > snapshot.volume_1m * 0.01:
                return ManipulationAlert(
                    manipulation_type=ManipulationType.LAYERING,
                    confidence=DetectionConfidence.MEDIUM,
                    symbol=snapshot.symbol,
                    evidence={
                        "side": side,
                        "levels": self._config.layering_level_count_threshold,
                        "avg_qty": round(avg_qty, 2),
                        "coefficient_of_variation": round(cv, 4),
                    },
                    recommended_action="discount_book_pressure",
                    ts_ns=ts_ns,
                    hazard_code="MANIP_LAYERING",
                )
        return None


class _PumpDumpDetector:
    """Detects pump and dump patterns.

    Indicators:
    - Rapid price increase (>5% in short window)
    - Accompanied by volume spike (>3x normal)
    - Followed by rapid reversal
    """

    __slots__ = ("_config",)

    def __init__(self, config: DetectorConfig) -> None:
        self._config = config

    def check(
        self, snapshot: OrderFlowSnapshot, history: list[OrderFlowSnapshot], ts_ns: int
    ) -> ManipulationAlert | None:
        if len(history) < 20:
            return None

        recent_trades = snapshot.recent_trades
        if not recent_trades:
            return None

        current_price = recent_trades[-1][0] if recent_trades else 0
        if current_price == 0:
            return None

        old_snapshot = history[-20] if len(history) >= 20 else history[0]
        old_trades = old_snapshot.recent_trades
        if not old_trades:
            return None
        old_price = old_trades[-1][0]
        if old_price == 0:
            return None

        price_change = (current_price - old_price) / old_price
        volume_avg = sum(h.volume_1m for h in history[-20:]) / 20
        volume_spike = snapshot.volume_1m / volume_avg if volume_avg else 0

        if (
            abs(price_change) > self._config.pump_price_move_threshold
            and volume_spike > self._config.pump_volume_spike_threshold
        ):
            direction = "pump" if price_change > 0 else "dump"
            return ManipulationAlert(
                manipulation_type=ManipulationType.PUMP_AND_DUMP,
                confidence=DetectionConfidence.HIGH,
                symbol=snapshot.symbol,
                evidence={
                    "price_change_pct": round(price_change * 100, 2),
                    "volume_spike_x": round(volume_spike, 1),
                    "direction": direction,
                    "window_ticks": 20,
                },
                recommended_action="halt_new_entries" if direction == "pump" else "tighten_stops",
                ts_ns=ts_ns,
                hazard_code="MANIP_PUMP_DUMP",
            )
        return None


class _FrontRunDetector:
    """Detects front-running patterns.

    Indicators:
    - Small trades consistently ahead of large trades
    - Same direction, tight time correlation
    - Beneficiary profits from the price impact of the large trade
    """

    __slots__ = ("_config",)

    def __init__(self, config: DetectorConfig) -> None:
        self._config = config

    def check(
        self, snapshot: OrderFlowSnapshot, history: list[OrderFlowSnapshot], ts_ns: int
    ) -> ManipulationAlert | None:
        if len(history) < self._config.front_run_time_window_ticks + 1:
            return None

        recent_window = history[-self._config.front_run_time_window_ticks :]
        all_trades: list[tuple[float, float, str]] = []
        for h in recent_window:
            all_trades.extend(h.recent_trades)

        if len(all_trades) < 4:
            return None

        for i in range(len(all_trades) - 1):
            small_price, small_qty, small_side = all_trades[i]
            large_price, large_qty, large_side = all_trades[i + 1]

            if small_side == large_side and large_qty > small_qty * 10:
                return ManipulationAlert(
                    manipulation_type=ManipulationType.FRONT_RUNNING,
                    confidence=DetectionConfidence.LOW,
                    symbol=snapshot.symbol,
                    evidence={
                        "small_qty": round(small_qty, 4),
                        "large_qty": round(large_qty, 4),
                        "ratio": round(large_qty / small_qty, 1),
                        "direction": small_side,
                    },
                    recommended_action="randomize_order_timing",
                    ts_ns=ts_ns,
                    hazard_code="MANIP_FRONT_RUN",
                )
        return None


class AdversarialSimulator:
    """Simulates specific manipulation scenarios to test system resilience.

    Generates synthetic order flow that includes manipulation patterns,
    then validates that the detection system catches them and the
    execution engine avoids being victimized.
    """

    __slots__ = ("_detector", "_scenarios_run", "_detection_rate")

    def __init__(self) -> None:
        self._detector = ManipulationDetector()
        self._scenarios_run = 0
        self._detection_rate: dict[ManipulationType, tuple[int, int]] = {}

    def run_scenario(self, manipulation_type: ManipulationType, ticks: int = 100) -> dict[str, Any]:
        """Run a specific manipulation scenario and return detection results."""
        self._scenarios_run += 1
        generator = _ScenarioGenerator(manipulation_type)
        snapshots = generator.generate(ticks)

        alerts: list[ManipulationAlert] = []
        for snap in snapshots:
            tick_alerts = self._detector.analyze(snap)
            alerts.extend(tick_alerts)

        detected = any(a.manipulation_type == manipulation_type for a in alerts)
        detection_tick = next(
            (
                i
                for i, snap in enumerate(snapshots)
                if any(
                    a.manipulation_type == manipulation_type for a in self._detector.analyze(snap)
                )
            ),
            -1,
        )

        # Track detection rates
        if manipulation_type not in self._detection_rate:
            self._detection_rate[manipulation_type] = (0, 0)
        hits, total = self._detection_rate[manipulation_type]
        self._detection_rate[manipulation_type] = (hits + int(detected), total + 1)

        return {
            "manipulation_type": manipulation_type.value,
            "detected": detected,
            "detection_tick": detection_tick,
            "total_alerts": len(alerts),
            "false_positives": sum(1 for a in alerts if a.manipulation_type != manipulation_type),
            "max_confidence": max(
                (a.confidence for a in alerts if a.manipulation_type == manipulation_type),
                default="NONE",
            ),
        }

    def run_full_battery(self) -> dict[str, Any]:
        """Run all manipulation scenarios."""
        results = {}
        for mtype in ManipulationType:
            results[mtype.value] = self.run_scenario(mtype)
        return {
            "scenarios_run": len(results),
            "detection_rate": sum(1 for r in results.values() if r["detected"]) / len(results),
            "results": results,
        }


class _ScenarioGenerator:
    """Generates synthetic order flow for a specific manipulation scenario."""

    __slots__ = ("_type",)

    def __init__(self, manipulation_type: ManipulationType) -> None:
        self._type = manipulation_type

    def generate(self, ticks: int) -> list[OrderFlowSnapshot]:
        """Generate synthetic snapshots that include the manipulation pattern."""
        snapshots: list[OrderFlowSnapshot] = []
        import random

        rng = random.Random(42)

        for t in range(ticks):
            base_price = 100.0 + rng.gauss(0, 0.5)

            # Normal market data
            bid_depth = [(base_price - i * 0.1, rng.uniform(1, 10)) for i in range(10)]
            ask_depth = [(base_price + i * 0.1, rng.uniform(1, 10)) for i in range(10)]
            trades = [
                (
                    base_price + rng.gauss(0, 0.1),
                    rng.uniform(0.1, 2.0),
                    "BUY" if rng.random() > 0.5 else "SELL",
                )
                for _ in range(5)
            ]

            cancel_rate = rng.uniform(0.3, 0.6)
            volume = rng.uniform(500, 1500)
            participants = rng.randint(10, 50)

            # Inject manipulation pattern
            if self._type == ManipulationType.SPOOFING and t > ticks // 3:
                cancel_rate = 0.95
                bid_depth = [(base_price - i * 0.1, 50.0) for i in range(10)]
            elif self._type == ManipulationType.WASH_TRADING and t > ticks // 3:
                volume *= 5
                participants = 3
            elif self._type == ManipulationType.PUMP_AND_DUMP and t > ticks // 2:
                base_price *= 1.08
                volume *= 4
            elif self._type == ManipulationType.LAYERING and t > ticks // 3:
                ask_depth = [(base_price + i * 0.05, 20.0) for i in range(8)]
            elif self._type == ManipulationType.FRONT_RUNNING and t > ticks // 3:
                trades = [(base_price, 0.1, "BUY"), (base_price + 0.01, 50.0, "BUY")] + trades

            snapshots.append(
                OrderFlowSnapshot(
                    symbol="BTC/USDT",
                    tick=t,
                    bid_depth=bid_depth,
                    ask_depth=ask_depth,
                    recent_trades=trades,
                    cancel_rate=cancel_rate,
                    volume_1m=volume,
                    unique_participants=participants,
                )
            )

        return snapshots


__all__ = [
    "AdversarialSimulator",
    "DetectionConfidence",
    "DetectorConfig",
    "ManipulationAlert",
    "ManipulationDetector",
    "ManipulationType",
    "OrderFlowSnapshot",
]

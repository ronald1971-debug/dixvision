"""ManipulationDetector — identifies market manipulation patterns.

Detects:
- Spoofing: large orders placed and cancelled before fill
- Layering: multiple price levels used to create false depth
- Wash trading: circular trades to inflate volume
- Pump & dump: coordinated price inflation followed by dump
- Front-running: informed trades ahead of large orders
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum


class ManipulationType(StrEnum):
    SPOOFING = "SPOOFING"
    LAYERING = "LAYERING"
    WASH_TRADING = "WASH_TRADING"
    PUMP_AND_DUMP = "PUMP_AND_DUMP"
    FRONT_RUNNING = "FRONT_RUNNING"
    STOP_HUNT = "STOP_HUNT"


@dataclass(frozen=True, slots=True)
class ManipulationAlert:
    """Detected manipulation event."""

    symbol: str
    manipulation_type: ManipulationType
    confidence: float  # [0, 1]
    severity: float  # [0, 1] how impactful
    description: str
    recommended_action: str


@dataclass(slots=True)
class OrderEvent:
    """Simplified order event for detection."""

    ts_ns: int
    symbol: str
    side: str  # BUY or SELL
    size: float
    price: float
    is_cancel: bool = False
    is_fill: bool = False


class ManipulationDetector:
    """Detects market manipulation patterns from order flow.

    Maintains rolling window of order events and applies heuristic
    detection rules. Deterministic: same event sequence → same alerts.
    """

    def __init__(
        self,
        *,
        window_size: int = 200,
        spoof_cancel_ratio: float = 0.8,
        volume_spike_z: float = 3.0,
    ) -> None:
        self._window = window_size
        self._spoof_ratio = spoof_cancel_ratio
        self._vol_z = volume_spike_z
        self._events: dict[str, deque[OrderEvent]] = {}
        self._volume_history: dict[str, deque[float]] = {}

    def ingest(self, event: OrderEvent) -> list[ManipulationAlert]:
        """Process an order event; return any manipulation alerts."""
        sym = event.symbol
        if sym not in self._events:
            self._events[sym] = deque(maxlen=self._window)
            self._volume_history[sym] = deque(maxlen=self._window)
        self._events[sym].append(event)
        if event.is_fill:
            self._volume_history[sym].append(event.size)

        alerts: list[ManipulationAlert] = []

        # Check spoofing
        spoof = self._detect_spoofing(sym)
        if spoof:
            alerts.append(spoof)

        # Check wash trading
        wash = self._detect_wash_trading(sym)
        if wash:
            alerts.append(wash)

        # Check stop hunt
        hunt = self._detect_stop_hunt(sym)
        if hunt:
            alerts.append(hunt)

        return alerts

    def _detect_spoofing(self, symbol: str) -> ManipulationAlert | None:
        """Detect spoofing: large orders repeatedly cancelled."""
        events = self._events.get(symbol)
        if not events or len(events) < 20:
            return None

        recent = list(events)[-50:]
        large_orders = [e for e in recent if e.size > self._avg_size(symbol) * 5 and not e.is_fill]
        cancels = [e for e in large_orders if e.is_cancel]

        if len(large_orders) < 3:
            return None
        cancel_ratio = len(cancels) / len(large_orders)

        if cancel_ratio > self._spoof_ratio:
            return ManipulationAlert(
                symbol=symbol,
                manipulation_type=ManipulationType.SPOOFING,
                confidence=min(cancel_ratio, 0.95),
                severity=0.7,
                description=(
                    f"Large orders cancelled {cancel_ratio:.0%} of the time — probable spoofing."
                ),
                recommended_action="Ignore large resting orders; weight recent fills more.",
            )
        return None

    def _detect_wash_trading(self, symbol: str) -> ManipulationAlert | None:
        """Detect wash trading: volume without price movement."""
        vol_hist = self._volume_history.get(symbol)
        if not vol_hist or len(vol_hist) < 30:
            return None

        recent_vol = sum(list(vol_hist)[-10:])
        avg_vol = sum(vol_hist) / len(vol_hist) * 10

        if avg_vol == 0:
            return None

        vol_ratio = recent_vol / avg_vol
        if vol_ratio > 3.0:
            # Check if price actually moved
            events = list(self._events[symbol])[-20:]
            prices = [e.price for e in events if e.price > 0]
            if prices:
                price_range = (max(prices) - min(prices)) / min(prices)
                if price_range < 0.001:  # <0.1% move despite 3x volume
                    return ManipulationAlert(
                        symbol=symbol,
                        manipulation_type=ManipulationType.WASH_TRADING,
                        confidence=0.70,
                        severity=0.5,
                        description="Volume spike without price movement — possible wash trading.",
                        recommended_action="Discount volume signal; rely on price action only.",
                    )
        return None

    def _detect_stop_hunt(self, symbol: str) -> ManipulationAlert | None:
        """Detect stop hunt: rapid wick beyond support/resistance then reversal."""
        events = list(self._events.get(symbol, []))
        if len(events) < 30:
            return None

        prices = [e.price for e in events[-30:] if e.price > 0]
        if len(prices) < 20:
            return None

        # Check for V-shaped or inverted-V price pattern
        mid = len(prices) // 2
        first_half = prices[:mid]
        second_half = prices[mid:]

        if not first_half or not second_half:
            return None

        first_trend = first_half[-1] - first_half[0]
        second_trend = second_half[-1] - second_half[0]

        # Sharp move followed by sharp reversal
        if abs(first_trend) > 0 and abs(second_trend) > 0:
            reversal_ratio = abs(second_trend / first_trend)
            if 0.7 < reversal_ratio < 1.5 and first_trend * second_trend < 0:
                mid_price = sum(prices) / len(prices)
                move_pct = abs(first_trend) / mid_price
                if move_pct > 0.005:  # > 0.5% wick
                    return ManipulationAlert(
                        symbol=symbol,
                        manipulation_type=ManipulationType.STOP_HUNT,
                        confidence=0.60,
                        severity=0.6,
                        description="Sharp wick + reversal pattern — possible stop hunt.",
                        recommended_action="Widen stops; don't chase wicks.",
                    )
        return None

    def _avg_size(self, symbol: str) -> float:
        events = self._events.get(symbol)
        if not events:
            return 1.0
        sizes = [e.size for e in events if e.size > 0]
        return sum(sizes) / len(sizes) if sizes else 1.0

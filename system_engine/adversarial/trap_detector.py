"""TrapDetector — detects false breakouts and price traps.

Identifies patterns designed to lure traders into bad positions:
- False breakout: price breaks level, then immediately reverses
- Liquidity sweep: quick wick to take out stops, then continue
- Bear/bull trap: appears like reversal, continues in original direction
- Fakeout: volume-less breakout that lacks conviction
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum


class TrapType(StrEnum):
    FALSE_BREAKOUT = "FALSE_BREAKOUT"
    LIQUIDITY_SWEEP = "LIQUIDITY_SWEEP"
    BEAR_TRAP = "BEAR_TRAP"
    BULL_TRAP = "BULL_TRAP"
    FAKEOUT = "FAKEOUT"


@dataclass(frozen=True, slots=True)
class TrapSignal:
    """Detected trap pattern."""

    symbol: str
    trap_type: TrapType
    confidence: float
    price_at_detection: float
    trap_level: float  # the price level that was the trap
    expected_reversal_direction: str  # UP or DOWN
    description: str


class TrapDetector:
    """Detects price trap patterns from price/volume data.

    Maintains rolling price/volume history and applies pattern
    recognition to identify common trap setups.
    """

    def __init__(self, *, lookback: int = 50, volume_confirmation_ratio: float = 0.5) -> None:
        self._lookback = lookback
        self._vol_confirm = volume_confirmation_ratio
        self._prices: dict[str, deque[float]] = {}
        self._volumes: dict[str, deque[float]] = {}
        self._highs: dict[str, deque[float]] = {}
        self._lows: dict[str, deque[float]] = {}

    def update(
        self,
        symbol: str,
        *,
        price: float,
        volume: float,
        high: float,
        low: float,
    ) -> list[TrapSignal]:
        """Update price/volume data; return any detected traps."""
        for store, val in [
            (self._prices, price),
            (self._volumes, volume),
            (self._highs, high),
            (self._lows, low),
        ]:
            if symbol not in store:
                store[symbol] = deque(maxlen=self._lookback)
            store[symbol].append(val)

        traps: list[TrapSignal] = []

        fb = self._detect_false_breakout(symbol, price, volume)
        if fb:
            traps.append(fb)

        sweep = self._detect_liquidity_sweep(symbol, price, low, high)
        if sweep:
            traps.append(sweep)

        return traps

    def _detect_false_breakout(
        self, symbol: str, current_price: float, current_volume: float
    ) -> TrapSignal | None:
        """Detect breakout on low volume (fakeout)."""
        prices = self._prices.get(symbol)
        volumes = self._volumes.get(symbol)
        if not prices or len(prices) < 20 or not volumes:
            return None

        hist_prices = list(prices)[:-1]
        hist_high = max(hist_prices[-15:])
        hist_low = min(hist_prices[-15:])
        avg_vol = sum(list(volumes)[:-1]) / (len(volumes) - 1)

        # Breakout above resistance on LOW volume
        if current_price > hist_high and current_volume < avg_vol * self._vol_confirm:
            return TrapSignal(
                symbol=symbol,
                trap_type=TrapType.FAKEOUT,
                confidence=0.65,
                price_at_detection=current_price,
                trap_level=hist_high,
                expected_reversal_direction="DOWN",
                description=(
                    f"Breakout above {hist_high:.4f} on"
                    f" {current_volume / avg_vol:.0%} of avg volume"
                    " — fakeout likely."
                ),
            )

        # Breakdown below support on LOW volume
        if current_price < hist_low and current_volume < avg_vol * self._vol_confirm:
            return TrapSignal(
                symbol=symbol,
                trap_type=TrapType.FAKEOUT,
                confidence=0.65,
                price_at_detection=current_price,
                trap_level=hist_low,
                expected_reversal_direction="UP",
                description=f"Breakdown below {hist_low:.4f} on weak volume — fakeout likely.",
            )

        return None

    def _detect_liquidity_sweep(
        self, symbol: str, price: float, low: float, high: float
    ) -> TrapSignal | None:
        """Detect liquidity sweep (wick beyond level + quick reversal)."""
        lows = self._lows.get(symbol)
        highs = self._highs.get(symbol)
        if not lows or len(lows) < 10 or not highs:
            return None

        hist_lows = list(lows)[:-3]
        hist_highs = list(highs)[:-3]
        if not hist_lows or not hist_highs:
            return None

        support = min(hist_lows[-10:])
        resistance = max(hist_highs[-10:])

        # Wick below support but close above it (sweep lows)
        if low < support and price > support:
            sweep_depth = (support - low) / support
            if sweep_depth > 0.002:  # at least 0.2% below
                return TrapSignal(
                    symbol=symbol,
                    trap_type=TrapType.LIQUIDITY_SWEEP,
                    confidence=0.70,
                    price_at_detection=price,
                    trap_level=support,
                    expected_reversal_direction="UP",
                    description=(
                        f"Swept below {support:.4f} then recovered — stops taken, reversal likely."
                    ),
                )

        # Wick above resistance but close below it
        if high > resistance and price < resistance:
            sweep_depth = (high - resistance) / resistance
            if sweep_depth > 0.002:
                return TrapSignal(
                    symbol=symbol,
                    trap_type=TrapType.LIQUIDITY_SWEEP,
                    confidence=0.70,
                    price_at_detection=price,
                    trap_level=resistance,
                    expected_reversal_direction="DOWN",
                    description=f"Swept above {resistance:.4f} then rejected — resistance holds.",
                )

        return None

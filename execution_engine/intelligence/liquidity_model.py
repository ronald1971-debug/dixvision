"""LiquidityModel — real-time liquidity assessment.

Models available liquidity across price levels to inform:
- Optimal order size (don't exceed available liquidity)
- Expected fill quality at different sizes
- Liquidity drought detection (thin books = danger)
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LiquiditySnapshot:
    """Point-in-time liquidity state for a symbol."""

    symbol: str
    ts_ns: int
    bid_depth_usd: float  # total bid-side liquidity in USD
    ask_depth_usd: float
    spread_bps: float
    top_of_book_size: float
    imbalance_ratio: float  # bid_depth / (bid_depth + ask_depth)
    is_thin: bool  # liquidity below threshold
    estimated_impact_1pct_bps: float  # est. impact of 1% ADV order


class LiquidityModel:
    """Tracks and predicts available market liquidity.

    Maintains rolling depth snapshots and computes liquidity metrics.
    Pure functional core; state is explicit and inspectable (INV-15).
    """

    def __init__(
        self,
        *,
        thin_threshold_usd: float = 10_000.0,
        window_size: int = 100,
    ) -> None:
        self._thin_threshold = thin_threshold_usd
        self._snapshots: dict[str, deque[LiquiditySnapshot]] = {}
        self._window = window_size

    def update(
        self,
        symbol: str,
        ts_ns: int,
        *,
        bids: list[tuple[float, float]],  # (price, size) levels
        asks: list[tuple[float, float]],
    ) -> LiquiditySnapshot:
        """Update liquidity model from order book snapshot."""
        bid_depth = sum(p * s for p, s in bids) if bids else 0.0
        ask_depth = sum(p * s for p, s in asks) if asks else 0.0
        total_depth = bid_depth + ask_depth

        spread_bps = 0.0
        top_size = 0.0
        if bids and asks:
            best_bid = bids[0][0]
            best_ask = asks[0][0]
            mid = (best_bid + best_ask) / 2
            spread_bps = ((best_ask - best_bid) / mid) * 10000 if mid > 0 else 0.0
            top_size = min(bids[0][1], asks[0][1])

        imbalance = bid_depth / total_depth if total_depth > 0 else 0.5
        is_thin = total_depth < self._thin_threshold

        # Estimate impact of 1% ADV order (simplified Kyle's lambda)
        estimated_impact = spread_bps * 2.5 if is_thin else spread_bps * 0.5

        snap = LiquiditySnapshot(
            symbol=symbol,
            ts_ns=ts_ns,
            bid_depth_usd=bid_depth,
            ask_depth_usd=ask_depth,
            spread_bps=spread_bps,
            top_of_book_size=top_size,
            imbalance_ratio=imbalance,
            is_thin=is_thin,
            estimated_impact_1pct_bps=estimated_impact,
        )

        if symbol not in self._snapshots:
            self._snapshots[symbol] = deque(maxlen=self._window)
        self._snapshots[symbol].append(snap)

        return snap

    def latest(self, symbol: str) -> LiquiditySnapshot | None:
        """Get latest snapshot for a symbol."""
        history = self._snapshots.get(symbol)
        return history[-1] if history else None

    def avg_spread_bps(self, symbol: str) -> float:
        """Rolling average spread."""
        history = self._snapshots.get(symbol)
        if not history:
            return 0.0
        return sum(s.spread_bps for s in history) / len(history)

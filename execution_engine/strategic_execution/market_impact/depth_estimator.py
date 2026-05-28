"""SE-04 — order-book depth estimator.

Estimates effective available depth from top-of-book levels. Pure computation.
INV-15. B1.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["DepthSnapshot", "DepthEstimator"]


@dataclass(frozen=True, slots=True)
class DepthSnapshot:
    symbol: str
    ts_ns: int
    bid_depth: float       # total bid qty within depth_bps of mid
    ask_depth: float       # total ask qty within depth_bps of mid
    depth_bps: float       # band used for measurement
    imbalance: float       # (bid - ask) / (bid + ask), range [-1, 1]


@dataclass(frozen=True, slots=True)
class _Level:
    price: float
    qty: float


class DepthEstimator:
    """Measure available order-book depth within a price band.

    Accepts a list of (price, qty) tuples for each side.
    """

    def __init__(self, depth_bps: float = 10.0) -> None:
        if depth_bps <= 0:
            raise ValueError("depth_bps must be positive")
        self._depth_bps = depth_bps

    def snapshot(
        self,
        symbol: str,
        ts_ns: int,
        mid_price: float,
        bids: list[tuple[float, float]],
        asks: list[tuple[float, float]],
    ) -> DepthSnapshot:
        band = mid_price * self._depth_bps / 10_000.0
        bid_depth = sum(qty for price, qty in bids if price >= mid_price - band)
        ask_depth = sum(qty for price, qty in asks if price <= mid_price + band)
        total = bid_depth + ask_depth
        imbalance = (bid_depth - ask_depth) / total if total > 0 else 0.0
        return DepthSnapshot(
            symbol=symbol,
            ts_ns=ts_ns,
            bid_depth=bid_depth,
            ask_depth=ask_depth,
            depth_bps=self._depth_bps,
            imbalance=imbalance,
        )

    def available_for_side(self, snapshot: DepthSnapshot, side: str) -> float:
        if side == "BUY":
            return snapshot.ask_depth
        if side == "SELL":
            return snapshot.bid_depth
        raise ValueError(f"Unknown side: {side!r}")

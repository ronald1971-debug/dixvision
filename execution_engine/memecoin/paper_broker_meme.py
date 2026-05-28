"""Paper broker for memecoin simulation (BUILD-DIRECTIVE — Tier 3).

Simulates memecoin trading with realistic characteristics:
- High slippage (8-15% for new launches)
- Partial fills based on on-chain liquidity
- MEV simulation (sandwich attacks, frontrunning)
- Transaction failure simulation (reverts, timeouts)
- Gas/priority fee tracking
- Honeypot simulation (sells may fail)

Uses the same deterministic approach as the main PaperBroker
but with memecoin-specific parameters.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum


class MemeOrderStatus(StrEnum):
    """Status of a memecoin paper order."""

    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    REVERTED = "REVERTED"
    TIMEOUT = "TIMEOUT"
    FRONTRUN = "FRONTRUN"
    REJECTED = "REJECTED"


@dataclass(slots=True)
class MemeFill:
    """A simulated memecoin fill."""

    order_id: str
    token_address: str
    side: str  # "buy" | "sell"
    requested_size_sol: float
    filled_size_sol: float
    price_per_token: float
    slippage_pct: float
    gas_sol: float
    priority_fee_sol: float
    status: MemeOrderStatus
    latency_ms: float
    ts_ns: int


class PaperBrokerMeme:
    """Paper trading broker for memecoin simulation.

    Simulates the full lifecycle of a memecoin trade including:
    - Realistic slippage (configurable per token age)
    - Partial fills based on simulated liquidity
    - Transaction failures (configurable revert rate)
    - MEV exposure (sandwich probability)
    - Gas costs
    """

    def __init__(
        self,
        *,
        initial_bankroll_sol: float = 10.0,
        default_slippage_pct: float = 12.0,
        gas_per_tx_sol: float = 0.0005,
        priority_fee_sol: float = 0.001,
        revert_rate: float = 0.05,  # 5% of txs revert
        sandwich_rate: float = 0.03,  # 3% get sandwiched
        min_liquidity_sol: float = 5.0,
    ) -> None:
        self._bankroll = initial_bankroll_sol
        self._default_slippage = default_slippage_pct
        self._gas = gas_per_tx_sol
        self._priority_fee = priority_fee_sol
        self._revert_rate = revert_rate
        self._sandwich_rate = sandwich_rate
        self._min_liquidity = min_liquidity_sol
        self._positions: dict[str, float] = {}  # token → amount held
        self._fills: list[MemeFill] = []
        self._fill_ring_size = 200

    def submit_buy(
        self,
        *,
        token_address: str,
        size_sol: float,
        pool_liquidity_sol: float = 50.0,
        token_age_seconds: int = 60,
        ts_ns: int = 0,
    ) -> MemeFill:
        """Simulate a memecoin buy order."""
        order_id = f"meme_buy_{len(self._fills)}"

        # Check bankroll
        total_cost = size_sol + self._gas + self._priority_fee
        if total_cost > self._bankroll:
            return self._make_fill(
                order_id,
                token_address,
                "buy",
                size_sol,
                0.0,
                0.0,
                0.0,
                MemeOrderStatus.REJECTED,
                0.0,
                ts_ns,
            )

        # Deterministic revert simulation
        if self._should_revert(token_address, ts_ns):
            # Still pay gas on revert
            self._bankroll -= self._gas
            return self._make_fill(
                order_id,
                token_address,
                "buy",
                size_sol,
                0.0,
                0.0,
                0.0,
                MemeOrderStatus.REVERTED,
                self._latency(token_address, ts_ns),
                ts_ns,
            )

        # Calculate slippage based on token age and liquidity
        slippage = self._calc_slippage(size_sol, pool_liquidity_sol, token_age_seconds)

        # Partial fill based on liquidity
        max_fillable = pool_liquidity_sol * 0.1  # max 10% of pool per trade
        filled_sol = min(size_sol, max_fillable)

        # Simulate price impact
        base_price = 0.000001  # placeholder — real price comes from pool state
        effective_price = base_price * (1 + slippage / 100.0)

        # Sandwich attack simulation
        status = MemeOrderStatus.FILLED
        if self._should_sandwich(token_address, ts_ns):
            slippage *= 1.5  # extra slippage from sandwich
            effective_price *= 1.05
            status = MemeOrderStatus.FRONTRUN

        if filled_sol < size_sol:
            status = MemeOrderStatus.PARTIAL

        # Deduct from bankroll
        cost = filled_sol + self._gas + self._priority_fee
        self._bankroll -= cost

        # Track position
        tokens_received = filled_sol / effective_price
        self._positions[token_address] = self._positions.get(token_address, 0.0) + tokens_received

        fill = self._make_fill(
            order_id,
            token_address,
            "buy",
            size_sol,
            filled_sol,
            effective_price,
            slippage,
            status,
            self._latency(token_address, ts_ns),
            ts_ns,
        )
        self._record_fill(fill)
        return fill

    def submit_sell(
        self,
        *,
        token_address: str,
        sell_pct: float = 1.0,  # sell this % of position
        pool_liquidity_sol: float = 50.0,
        is_honeypot: bool = False,
        ts_ns: int = 0,
    ) -> MemeFill:
        """Simulate a memecoin sell order."""
        order_id = f"meme_sell_{len(self._fills)}"
        position = self._positions.get(token_address, 0.0)

        if position <= 0:
            return self._make_fill(
                order_id,
                token_address,
                "sell",
                0.0,
                0.0,
                0.0,
                0.0,
                MemeOrderStatus.REJECTED,
                0.0,
                ts_ns,
            )

        # Honeypot: sell reverts
        if is_honeypot:
            self._bankroll -= self._gas
            return self._make_fill(
                order_id,
                token_address,
                "sell",
                position * sell_pct,
                0.0,
                0.0,
                0.0,
                MemeOrderStatus.REVERTED,
                self._latency(token_address, ts_ns),
                ts_ns,
            )

        tokens_to_sell = position * sell_pct
        base_price = 0.000001  # placeholder
        size_sol = tokens_to_sell * base_price

        slippage = self._calc_slippage(size_sol, pool_liquidity_sol, 3600)
        effective_sol = size_sol * (1 - slippage / 100.0)

        # Deduct gas, add proceeds
        self._bankroll += effective_sol - self._gas - self._priority_fee
        self._positions[token_address] -= tokens_to_sell

        fill = self._make_fill(
            order_id,
            token_address,
            "sell",
            size_sol,
            effective_sol,
            base_price * (1 - slippage / 100.0),
            slippage,
            MemeOrderStatus.FILLED,
            self._latency(token_address, ts_ns),
            ts_ns,
        )
        self._record_fill(fill)
        return fill

    @property
    def bankroll(self) -> float:
        """Current SOL bankroll."""
        return self._bankroll

    @property
    def active_positions(self) -> dict[str, float]:
        """Current token positions."""
        return {k: v for k, v in self._positions.items() if v > 0}

    @property
    def recent_fills(self) -> list[MemeFill]:
        """Recent fills (ring buffer)."""
        return list(self._fills)

    def _calc_slippage(self, size_sol: float, liquidity_sol: float, age_seconds: int) -> float:
        """Calculate realistic slippage."""
        # Base: configured default
        base = self._default_slippage
        # Size impact: larger trades = more slippage
        size_impact = (size_sol / max(liquidity_sol, 1.0)) * 50.0
        # Age impact: younger tokens = more volatile
        age_factor = max(0.5, 1.0 - (age_seconds / 3600.0) * 0.5)
        return min(base * age_factor + size_impact, 25.0)  # cap at 25%

    def _should_revert(self, token: str, ts_ns: int) -> bool:
        """Deterministic revert simulation."""
        h = int(hashlib.sha256(f"{token}:{ts_ns}:revert".encode()).hexdigest()[:8], 16)
        return (h % 100) < (self._revert_rate * 100)

    def _should_sandwich(self, token: str, ts_ns: int) -> bool:
        """Deterministic sandwich attack simulation."""
        h = int(hashlib.sha256(f"{token}:{ts_ns}:sandwich".encode()).hexdigest()[:8], 16)
        return (h % 100) < (self._sandwich_rate * 100)

    def _latency(self, token: str, ts_ns: int) -> float:
        """Deterministic latency simulation (ms)."""
        h = int(hashlib.sha256(f"{token}:{ts_ns}:lat".encode()).hexdigest()[:4], 16)
        return 200.0 + (h % 3000)  # 200ms to 3200ms for on-chain

    def _make_fill(
        self,
        order_id: str,
        token: str,
        side: str,
        requested: float,
        filled: float,
        price: float,
        slippage: float,
        status: MemeOrderStatus,
        latency: float,
        ts_ns: int,
    ) -> MemeFill:
        return MemeFill(
            order_id=order_id,
            token_address=token,
            side=side,
            requested_size_sol=requested,
            filled_size_sol=filled,
            price_per_token=price,
            slippage_pct=slippage,
            gas_sol=self._gas,
            priority_fee_sol=self._priority_fee,
            status=status,
            latency_ms=latency,
            ts_ns=ts_ns,
        )

    def _record_fill(self, fill: MemeFill) -> None:
        self._fills.append(fill)
        if len(self._fills) > self._fill_ring_size:
            self._fills = self._fills[-self._fill_ring_size :]

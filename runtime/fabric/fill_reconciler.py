"""Fill Reconciler — fill events → position update → risk (CONVERGENCE PILLAR 2).

Processes execution fills and reconciles them against expected state:
1. Validates fill matches an outstanding order
2. Updates position state
3. Triggers risk snapshot recalculation
4. Updates RuntimeAuthority with new positions/exposure
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, auto

from runtime.authority import RuntimeAuthorityStore, WriterToken


class FillStatus(StrEnum):
    """Status of a fill reconciliation."""

    MATCHED = auto()
    PARTIAL = auto()
    UNEXPECTED = auto()
    REJECTED = auto()


@dataclass(frozen=True, slots=True)
class Fill:
    """A fill event from an adapter."""

    fill_id: str
    order_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    fee_usd: float
    ts_ns: int
    adapter_name: str


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """Result of reconciling a fill."""

    fill: Fill
    status: FillStatus
    position_delta: float
    exposure_delta_usd: float
    pnl_delta_usd: float


@dataclass(frozen=True, slots=True)
class ReconcilerMetrics:
    """Reconciler telemetry."""

    fills_processed: int = 0
    matched_count: int = 0
    unexpected_count: int = 0
    total_pnl_usd: float = 0.0


class FillReconciler:
    """Reconciles fills and updates RuntimeAuthority.

    Maintains expected orders and validates fills against them.
    Updates positions, exposure, and PnL in the authority store.
    """

    def __init__(
        self,
        *,
        store: RuntimeAuthorityStore,
        writer_token: WriterToken,
    ) -> None:
        self._store = store
        self._writer = writer_token
        self._pending_orders: dict[str, dict[str, object]] = {}
        self._positions: dict[str, float] = {}
        self._metrics = ReconcilerMetrics()

    @property
    def metrics(self) -> ReconcilerMetrics:
        return self._metrics

    def register_order(
        self,
        *,
        order_id: str,
        symbol: str,
        side: str,
        expected_quantity: float,
    ) -> None:
        """Register an order that we expect fills for."""
        self._pending_orders[order_id] = {
            "symbol": symbol,
            "side": side,
            "expected_quantity": expected_quantity,
            "filled_quantity": 0.0,
        }

    def reconcile(self, fill: Fill) -> ReconciliationResult:
        """Reconcile a fill against pending orders.

        Updates RuntimeAuthority with new position state.
        """
        order = self._pending_orders.get(fill.order_id)

        if order is None:
            # Unexpected fill — no matching order
            self._metrics = ReconcilerMetrics(
                fills_processed=self._metrics.fills_processed + 1,
                matched_count=self._metrics.matched_count,
                unexpected_count=self._metrics.unexpected_count + 1,
                total_pnl_usd=self._metrics.total_pnl_usd,
            )
            return ReconciliationResult(
                fill=fill,
                status=FillStatus.UNEXPECTED,
                position_delta=0.0,
                exposure_delta_usd=0.0,
                pnl_delta_usd=0.0,
            )

        # Update position
        position_delta = fill.quantity if fill.side == "BUY" else -fill.quantity
        self._positions[fill.symbol] = self._positions.get(fill.symbol, 0.0) + position_delta

        exposure_delta = fill.quantity * fill.price
        pnl_delta = -fill.fee_usd  # Simplified — real PnL needs entry price tracking

        # Determine if order is fully filled
        filled = float(order["filled_quantity"]) + fill.quantity
        order["filled_quantity"] = filled
        expected = float(order["expected_quantity"])
        status = FillStatus.MATCHED if filled >= expected else FillStatus.PARTIAL

        if status == FillStatus.MATCHED:
            del self._pending_orders[fill.order_id]

        # Update RuntimeAuthority
        total_exposure = sum(abs(qty) * fill.price for qty in self._positions.values())
        open_positions = sum(1 for qty in self._positions.values() if qty != 0.0)

        self._writer.write(
            fill.ts_ns,
            open_positions=open_positions,
            total_exposure_usd=total_exposure,
        )

        self._metrics = ReconcilerMetrics(
            fills_processed=self._metrics.fills_processed + 1,
            matched_count=self._metrics.matched_count + 1,
            unexpected_count=self._metrics.unexpected_count,
            total_pnl_usd=self._metrics.total_pnl_usd + pnl_delta,
        )

        return ReconciliationResult(
            fill=fill,
            status=status,
            position_delta=position_delta,
            exposure_delta_usd=exposure_delta,
            pnl_delta_usd=pnl_delta,
        )

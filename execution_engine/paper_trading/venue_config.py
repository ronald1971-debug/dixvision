"""execution_engine.paper_trading.venue_config — Venue-realistic paper parameters.

Each VenueConfig captures the fee structure, slippage model, and latency
profile of its real exchange counterpart so paper fills are economically
representative.  All figures are conservative real-world approximations.

Sources:
  Binance   — 0.075 % taker (BNB discount applied); 50 ms median REST latency
  Coinbase  — 0.25 % taker / 0.15 % maker (Starter tier); ~80 ms
  Kraken    — 0.26 % taker / 0.16 % maker (Starter tier); ~70 ms
  Alpaca    — 0 commission (equity + crypto paper); ~30 ms
  OANDA     — 1-pip spread ~10 bps (EUR/USD); ~100 ms practice-API
  IBKR      — 0.05 % tiered (US equity fixed); ~40 ms TWS paper port

INV-08: frozen=True, slots=True.
Authority: stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VenueConfig:
    """Paper-trading configuration for one exchange venue.

    Attributes:
        name: Adapter identifier registered in the AdapterRegistry.
        venue: Human-readable venue tag shown in fills + dashboard.
        exchange: Short exchange name (used in snapshots / dashboard labels).
        asset_class: Primary asset class label ("crypto", "equity", "forex", "multi").
        initial_cash: Virtual cash balance at reset / first construction.
        slippage_bps: Linear fill slippage in basis points.
        taker_fee_bps: Taker commission in basis points.
        maker_fee_bps: Maker rebate/commission in basis points.
        latency_ns_base: Deterministic constant latency stamp delta (ns).
        latency_ns_jitter: Deterministic jitter window width (ns).
        default_qty: Default order quantity when signal carries no qty.
        fill_ring_size: Capacity of the recent-fill ring.
    """

    name: str
    venue: str
    exchange: str
    asset_class: str
    initial_cash: float
    slippage_bps: float
    taker_fee_bps: float
    maker_fee_bps: float
    latency_ns_base: int
    latency_ns_jitter: int
    default_qty: float = 1.0
    fill_ring_size: int = 512


# ---------------------------------------------------------------------------
# Six canonical venue configurations
# ---------------------------------------------------------------------------

BINANCE_PAPER = VenueConfig(
    name="binance_paper",
    venue="binance:paper",
    exchange="Binance",
    asset_class="crypto",
    initial_cash=10_000.0,
    slippage_bps=5.0,
    taker_fee_bps=7.5,        # 0.075 % standard spot taker
    maker_fee_bps=7.5,
    latency_ns_base=50_000_000,    # 50 ms
    latency_ns_jitter=20_000_000,  # ± 20 ms
    default_qty=0.001,             # ~1 BTC unit / small default
)

COINBASE_PAPER = VenueConfig(
    name="coinbase_paper",
    venue="coinbase:paper",
    exchange="Coinbase",
    asset_class="crypto",
    initial_cash=10_000.0,
    slippage_bps=8.0,
    taker_fee_bps=25.0,       # 0.25 % Advanced Trade Starter taker
    maker_fee_bps=15.0,       # 0.15 % maker
    latency_ns_base=80_000_000,
    latency_ns_jitter=30_000_000,
    default_qty=0.001,
)

KRAKEN_PAPER = VenueConfig(
    name="kraken_paper",
    venue="kraken:paper",
    exchange="Kraken",
    asset_class="crypto",
    initial_cash=10_000.0,
    slippage_bps=6.0,
    taker_fee_bps=26.0,       # 0.26 % Starter taker
    maker_fee_bps=16.0,       # 0.16 % maker
    latency_ns_base=70_000_000,
    latency_ns_jitter=25_000_000,
    default_qty=0.001,
)

ALPACA_PAPER = VenueConfig(
    name="alpaca_paper",
    venue="alpaca:paper",
    exchange="Alpaca",
    asset_class="equity",
    initial_cash=100_000.0,   # IBKR/Alpaca paper accounts start with 100k
    slippage_bps=3.0,
    taker_fee_bps=0.0,        # commission-free US equities + crypto
    maker_fee_bps=0.0,
    latency_ns_base=30_000_000,
    latency_ns_jitter=10_000_000,
    default_qty=1.0,           # 1 share default
)

OANDA_PAPER = VenueConfig(
    name="oanda_paper",
    venue="oanda:paper",
    exchange="OANDA",
    asset_class="forex",
    initial_cash=50_000.0,
    slippage_bps=15.0,        # forex spread cost (~1.5 pip EUR/USD)
    taker_fee_bps=10.0,       # spread equivalent fee (EUR/USD ≈ 1 pip = 10 bps)
    maker_fee_bps=10.0,
    latency_ns_base=100_000_000,
    latency_ns_jitter=40_000_000,
    default_qty=1000.0,       # 1 micro lot = 1000 units
)

IBKR_PAPER = VenueConfig(
    name="ibkr_paper",
    venue="ibkr:paper",
    exchange="IBKR",
    asset_class="multi",
    initial_cash=100_000.0,
    slippage_bps=4.0,
    taker_fee_bps=5.0,        # IBKR Tiered ~0.05 % US equity
    maker_fee_bps=3.0,
    latency_ns_base=40_000_000,
    latency_ns_jitter=15_000_000,
    default_qty=1.0,
)


VENUE_CONFIGS: dict[str, VenueConfig] = {
    cfg.name: cfg
    for cfg in (
        BINANCE_PAPER,
        COINBASE_PAPER,
        KRAKEN_PAPER,
        ALPACA_PAPER,
        OANDA_PAPER,
        IBKR_PAPER,
    )
}


__all__ = [
    "ALPACA_PAPER",
    "BINANCE_PAPER",
    "COINBASE_PAPER",
    "IBKR_PAPER",
    "KRAKEN_PAPER",
    "OANDA_PAPER",
    "VENUE_CONFIGS",
    "VenueConfig",
]

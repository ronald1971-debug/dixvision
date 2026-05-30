"""execution_engine.paper_trading — Credential-free paper trading ecosystem.

Stage 9 of DIX VISION v42.2.

Six venue adapters (Binance, Coinbase, Kraken, Alpaca, OANDA, IBKR) operating
in deterministic paper mode — no credentials required, always READY.

Entry points:
    get_paper_trading_hub()  — the process-wide hub singleton
    VENUE_CONFIGS            — VenueConfig for each of the six exchanges
"""

from execution_engine.paper_trading.adapter import PaperVenueAdapter
from execution_engine.paper_trading.hub import PaperTradingHub, get_paper_trading_hub
from execution_engine.paper_trading.venue_config import (
    ALPACA_PAPER,
    BINANCE_PAPER,
    COINBASE_PAPER,
    IBKR_PAPER,
    KRAKEN_PAPER,
    OANDA_PAPER,
    VENUE_CONFIGS,
    VenueConfig,
)

__all__ = [
    "ALPACA_PAPER",
    "BINANCE_PAPER",
    "COINBASE_PAPER",
    "IBKR_PAPER",
    "KRAKEN_PAPER",
    "OANDA_PAPER",
    "VENUE_CONFIGS",
    "PaperTradingHub",
    "PaperVenueAdapter",
    "VenueConfig",
    "get_paper_trading_hub",
]

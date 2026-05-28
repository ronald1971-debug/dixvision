"""trading.py — Paper Trading CLI Entry Point.

Lightweight entry point for running paper trading simulations without
the full UI harness. Useful for CI, batch backtesting, and headless
operation.

Boots the system in PAPER mode, connects the PaperBroker, runs the
intelligence → governance → execution loop for a specified duration
or until interrupted.

Usage:
    python trading.py --symbol BTCUSDT --duration 3600
    python trading.py --backtest --from 2024-01-01 --to 2024-06-01
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def place_trade(
    symbol: str = "BTCUSDT",
    trade_size_pct: float = 0.0,
    *,
    size_usd: float | None = None,
    portfolio_usd: float | None = None,
) -> str:
    """Execute a governed paper trade.

    Passes through the full enforcement pipeline (governance kernel +
    risk cache).  Returns a confirmation string on success; raises
    ``RuntimeError`` if governance rejects the action.
    """
    from enforcement.decorators import enforce_full

    @enforce_full
    def _do_trade(
        symbol: str,
        trade_size_pct: float,
        size_usd: float | None = None,
        portfolio_usd: float | None = None,
    ) -> str:
        return f"executed paper trade: {symbol} @ {trade_size_pct}%"

    return _do_trade(
        symbol,
        trade_size_pct,
        size_usd=size_usd,
        portfolio_usd=portfolio_usd,
    )


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for paper trading."""
    parser = argparse.ArgumentParser(description="DIX VISION Paper Trading")
    parser.add_argument("--symbol", type=str, default="BTCUSDT", help="Trading symbol")
    parser.add_argument(
        "--duration", type=int, default=0, help="Run duration in seconds (0=infinite)"
    )
    parser.add_argument("--backtest", action="store_true", help="Backtest mode")
    parser.add_argument("--from-date", type=str, default="", help="Backtest start (YYYY-MM-DD)")
    parser.add_argument("--to-date", type=str, default="", help="Backtest end (YYYY-MM-DD)")
    parser.add_argument("--initial-balance", type=float, default=100_000.0)
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


async def run_paper_trading(args: argparse.Namespace) -> None:
    """Run the paper trading loop."""
    from core.time_source import FixedClock, WallClock

    clock = FixedClock() if args.backtest else WallClock()
    logging.info(
        "Paper trading: symbol=%s, mode=%s, balance=%.0f",
        args.symbol,
        "backtest" if args.backtest else "paper",
        args.initial_balance,
    )

    # Initialize paper broker
    try:
        from execution_engine.adapters.paper import PaperBroker

        broker = PaperBroker(initial_balance=args.initial_balance)
        logging.info("PaperBroker initialized with $%.0f", args.initial_balance)
    except ImportError:
        logging.warning("PaperBroker not available, using simulation stub")
        broker = None

    # Run loop
    tick = 0
    try:
        while True:
            tick += 1
            ts = clock.now_ns()

            if tick % 100 == 0:
                logging.info("Tick %d at %d", tick, ts)

            if args.duration > 0 and tick >= args.duration:
                logging.info("Duration reached (%d ticks)", tick)
                break

            await asyncio.sleep(0.01 if not args.backtest else 0)

    except KeyboardInterrupt:
        pass

    # Report results
    if broker is not None:
        logging.info("Session complete: %d ticks", tick)
    else:
        logging.info("Dry run complete: %d ticks", tick)


def main() -> None:
    """CLI entry point."""
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )
    try:
        asyncio.run(run_paper_trading(args))
    except KeyboardInterrupt:
        logging.info("Trading stopped by operator")


if __name__ == "__main__":
    main()

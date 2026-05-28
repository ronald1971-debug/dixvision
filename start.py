"""start.py — DIX VISION v42.2 Main Entry Point.

Production entry point that boots the entire system in the correct order:
1. Load immutable safety axioms + kill switch
2. Initialize TimeAuthority (WallClock for production)
3. Load operator authority from registry/operator.yaml
4. Boot governance engine (StateTransitionManager → FSM)
5. Boot intelligence engine (Indira)
6. Boot execution engine (adapters + gate)
7. Boot learning engine (vector memory + evolution pipeline)
8. Boot system engine (health monitors + heartbeat)
9. Start FastAPI server (UI harness + API routes)
10. Auto-start all plugins + feeds

The system boots in PAPER mode with Learning=FULL, Practice=ON,
LiveExecution=BLOCKED per registry/operator.yaml defaults.

Usage:
    python start.py [--port 8000] [--mode paper] [--no-feeds]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Ensure project root on sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="DIX VISION v42.2")
    parser.add_argument("--port", type=int, default=8000, help="API server port")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Bind host")
    parser.add_argument("--mode", choices=["paper", "live"], default="paper")
    parser.add_argument("--no-feeds", action="store_true", help="Skip auto-start feeds")
    parser.add_argument("--no-plugins", action="store_true", help="Skip plugin auto-load")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser.parse_args()


async def boot_system(args: argparse.Namespace) -> None:
    """Boot the system in the correct dependency order."""
    from core.time_source import WallClock
    from immutable_core.constants import AXIOMS, SYSTEM_NAME, SYSTEM_VERSION

    clock = WallClock()
    boot_ts = clock.now_ns()

    logging.info("%s %s booting at %d", SYSTEM_NAME, SYSTEM_VERSION, boot_ts)
    logging.info(
        "Safety axioms loaded: max_drawdown=%.1f%%, fail_closed=%s",
        AXIOMS.MAX_DRAWDOWN_FLOOR_PCT,
        AXIOMS.FAIL_CLOSED,
    )

    # Load operator authority
    try:
        from ui.server import create_app

        app = create_app()
        logging.info("Operator authority loaded from registry/operator.yaml")
    except Exception as e:
        logging.error("Failed to create app: %s", e)
        sys.exit(1)

    # Start server
    import uvicorn

    config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        log_level="debug" if args.debug else "info",
        access_log=args.debug,
    )
    server = uvicorn.Server(config)
    logging.info("Starting server on %s:%d (mode=%s)", args.host, args.port, args.mode)
    await server.serve()


def main() -> None:
    """Main entry point."""
    args = parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    try:
        asyncio.run(boot_system(args))
    except KeyboardInterrupt:
        logging.info("Operator shutdown (Ctrl+C)")
    except Exception as e:
        logging.critical("Fatal boot failure: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()

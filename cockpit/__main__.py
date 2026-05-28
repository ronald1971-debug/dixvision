"""cockpit.__main__ — Operator Cockpit CLI Entry Point.

Launches the operator cockpit (IDE-like interface) that provides:
- Live system state monitoring
- REPL for operator commands
- Signal stream display
- Quick-action shortcuts (kill switch, mode transitions, authority flips)

The cockpit connects to the running server's WebSocket for live updates
and provides a TUI for operators who prefer terminal over browser.

Usage:
    python -m cockpit [--host localhost] [--port 8000]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def parse_args() -> argparse.Namespace:
    """Parse cockpit CLI arguments."""
    parser = argparse.ArgumentParser(description="DIX VISION Operator Cockpit")
    parser.add_argument("--host", default="localhost", help="Server host")
    parser.add_argument("--port", type=int, default=8000, help="Server port")
    parser.add_argument(
        "--mode",
        choices=["tui", "repl"],
        default="repl",
        help="Cockpit mode (tui=full terminal UI, repl=command line)",
    )
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


async def run_repl(host: str, port: int) -> None:
    """Run the operator REPL connected to the server."""
    import aiohttp

    base_url = f"http://{host}:{port}"

    print(f"DIX VISION Cockpit — connecting to {base_url}")
    print("Commands: status, mode, authority, kill, signals, quit")
    print()

    async with aiohttp.ClientSession() as session:
        # Verify server is reachable
        try:
            async with session.get(f"{base_url}/api/health") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"Connected. Mode: {data.get('mode', 'unknown')}")
                else:
                    print(f"Warning: server returned {resp.status}")
        except Exception as e:
            print(f"Cannot reach server at {base_url}: {e}")
            print("Is the server running? Start with: python start.py")
            return

        # REPL loop
        while True:
            try:
                cmd = await asyncio.to_thread(input, "cockpit> ")
            except (EOFError, KeyboardInterrupt):
                print("\nExiting cockpit.")
                break

            cmd = cmd.strip().lower()
            if cmd in ("quit", "exit", "q"):
                break
            elif cmd == "status":
                async with session.get(f"{base_url}/api/state") as resp:
                    data = await resp.json()
                    print(f"  Mode: {data.get('mode', '?')}")
                    print(f"  Health: {data.get('health', '?')}")
                    print(f"  Tick: {data.get('tick_count', 0)}")
            elif cmd == "authority":
                async with session.get(f"{base_url}/api/operator/authority") as resp:
                    data = await resp.json()
                    print(f"  Learning: {data.get('learning', '?')}")
                    print(f"  Practice: {data.get('practice', '?')}")
                    print(f"  LiveExecution: {data.get('live_execution', '?')}")
            elif cmd == "kill":
                confirm = await asyncio.to_thread(input, "  Confirm kill switch? [y/N]: ")
                if confirm.strip().lower() == "y":
                    async with session.post(f"{base_url}/api/kill_switch") as resp:
                        print(f"  Kill switch: {resp.status}")
            elif cmd == "signals":
                async with session.get(f"{base_url}/api/signals/latest") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for sig in data.get("signals", [])[:5]:
                            print(
                                f"  {sig.get('symbol', '?')} {sig.get('direction', '?')} "
                                f"conf={sig.get('confidence', 0):.2f}"
                            )
                    else:
                        print("  No signals available")
            elif cmd == "help":
                print("  status    — show system state")
                print("  authority — show operator switches")
                print("  kill      — trigger kill switch")
                print("  signals   — latest intelligence signals")
                print("  quit      — exit cockpit")
            else:
                print(f"  Unknown command: {cmd}. Type 'help' for options.")


def main() -> None:
    """Entry point for the cockpit."""
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(message)s",
    )
    try:
        asyncio.run(run_repl(args.host, args.port))
    except KeyboardInterrupt:
        print("\nCockpit closed.")


if __name__ == "__main__":
    main()

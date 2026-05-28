"""
main.py
DIX VISION v42.2 — Runtime Launcher

Boot modes:
    python main.py --verify       Foundation + governance checks only
    python main.py --legacy       Old simulated market loop (pre-convergence)
    python main.py                Full runtime kernel (converged)
    python main.py --dev          Dev environment (permissive)

The default mode boots through the RuntimeConvergence layer which provides:
    - Single RuntimeAuthorityStore (one truth)
    - Deterministic tick loop (ingest → decide → GOVERN → execute → reconcile)
    - Blocking EnforcementGate (every intent HMAC-signed)
    - SessionRecorder (every event captured for replay)
    - CCXT exchange binding (real when connected, paper otherwise)
"""

from __future__ import annotations

import asyncio
import signal as signal_mod
import sys


def main() -> None:
    from bootstrap_kernel import run
    from system.logger import get_logger
    from system.state import get_state_manager

    env = "dev" if "--dev" in sys.argv else "prod"
    verify_only = "--verify" in sys.argv
    legacy_mode = "--legacy" in sys.argv

    # Phase 1: Legacy boot sequence (foundation, config, ledger, governance)
    run(env=env, verify_only=verify_only)
    if verify_only:
        return

    log = get_logger("main")
    state_mgr = get_state_manager()

    if legacy_mode:
        _run_legacy_loop(log, state_mgr)
    else:
        _run_converged(log, state_mgr)


def _run_converged(log, state_mgr) -> None:
    """Boot and run the converged runtime kernel."""
    from runtime.convergence import get_convergence

    convergence = get_convergence()

    log.info("[MAIN] Booting converged runtime kernel...")
    print("\n[DIX VISION v42.2] Converged runtime starting...\n")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _boot_and_run() -> None:
        boot_ok = await convergence.boot()
        if boot_ok:
            log.info("[MAIN] Kernel booted — entering operational loop")
            print("[DIX VISION v42.2] System ONLINE (converged). Press Ctrl+C to stop.\n")
        else:
            log.warning("[MAIN] Kernel booted in DEGRADED mode")
            print("[DIX VISION v42.2] System DEGRADED. Press Ctrl+C to stop.\n")

        await convergence.run_forever()

    def _shutdown(sig, frame):
        print("\n[DIX VISION] Shutdown signal received...")
        loop.run_until_complete(convergence.stop())
        state_mgr.set_mode("HALTED")
        from enforcement.runtime_guardian import get_runtime_guardian

        get_runtime_guardian().stop()
        from execution.engine import get_dyon_engine

        get_dyon_engine().stop()
        sys.exit(0)

    signal_mod.signal(signal_mod.SIGINT, _shutdown)
    signal_mod.signal(signal_mod.SIGTERM, _shutdown)

    try:
        loop.run_until_complete(_boot_and_run())
    except KeyboardInterrupt:
        loop.run_until_complete(convergence.stop())
    finally:
        loop.close()


def _run_legacy_loop(log, state_mgr) -> None:
    """Legacy simulated market loop (pre-convergence, retained for testing)."""
    import math
    import time

    from execution.engine import get_dyon_engine
    from mind.engine import IndiraEngine
    from system.health_monitor import get_health_monitor

    health = get_health_monitor()
    indira = IndiraEngine()

    log.info("[MAIN] Entering LEGACY trading loop (--legacy)")
    print("\n[DIX VISION v42.2] System ONLINE (legacy). Press Ctrl+C to stop.\n")

    def _shutdown(sig, frame):
        print("\n[DIX VISION] Shutdown signal received...")
        state_mgr.set_mode("HALTED")
        dyon = get_dyon_engine()
        dyon.stop()
        from enforcement.runtime_guardian import get_runtime_guardian

        get_runtime_guardian().stop()
        sys.exit(0)

    signal_mod.signal(signal_mod.SIGINT, _shutdown)
    signal_mod.signal(signal_mod.SIGTERM, _shutdown)

    tick = 0
    while True:
        state_mgr.heartbeat()
        tick += 1

        signal_val = math.sin(tick * 0.1) * 0.8
        market_data = {
            "signal": signal_val,
            "asset": "BTCUSDT",
            "price": 65_000.0 + (signal_val * 500),
            "data_quality": 0.95,
            "execution_confidence": 0.90,
            "strategy": "regime_adaptive",
        }

        ev = indira.process_tick(market_data)
        if ev.event_type != "HOLD" and tick % 20 == 0:
            log.info(
                f"Indira: {ev.event_type} {ev.asset} side={ev.side} "
                f"size_usd={ev.size_usd:.0f} "
                f"latency_ms={ev.latency_ns / 1e6:.2f}"
            )

        if tick % 60 == 0:
            health.print_status()

        time.sleep(0.1)


if __name__ == "__main__":
    main()

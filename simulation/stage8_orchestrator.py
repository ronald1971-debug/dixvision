"""simulation.stage8_orchestrator — Stage 8 Simulation Dominance Orchestrator.

Boots all 9 specialist engines, drives a shared tick loop, and merges
snapshots into a single unified simulation report.

Engines:
  1. SyntheticMarketEngine     — GBM + Heston + Merton jump-diffusion
  2. AdversarialTraderArena    — 5-agent adversarial arena
  3. ReflexiveSimulationEngine — Soros reflexivity + momentum cascades
  4. LiquidityWarfareEngine    — spoofing, layering, depth erosion
  5. CrowdPsychologyEngine     — 7-state sentiment machine, herding
  6. VolatilityCascadeEngine   — regime transitions, gamma squeeze
  7. MacroStressEngine         — 9 macro scenarios, composite stress index
  8. ExchangeFailureEngine     — 5 venues, multi-state failure/recovery
  9. LatencyWarfareEngine      — 4 tiers, queue dynamics, adverse selection

Cross-engine signal routing (per tick):
  market → price_return  → reflexive, crowd, vol_cascade
  vol_cascade → vol      → crowd, liquidity, latency (market_activity)
  macro_stress → stress  → vol_cascade, exchange_failure (indirectly)
  exchange → fill_rate   → latency market_activity scaling
"""
from __future__ import annotations

import threading
import time
from typing import Any

from simulation.engines.synthetic_market    import get_synthetic_market_engine
from simulation.engines.adversarial_arena   import get_adversarial_arena
from simulation.engines.reflexive           import get_reflexive_engine
from simulation.engines.liquidity_warfare   import get_liquidity_warfare_engine
from simulation.engines.crowd_psychology    import get_crowd_psychology_engine
from simulation.engines.volatility_cascade  import get_volatility_cascade_engine
from simulation.engines.macro_stress        import get_macro_stress_engine
from simulation.engines.exchange_failure    import get_exchange_failure_engine
from simulation.engines.latency_warfare     import get_latency_warfare_engine


class Stage8SimulationOrchestrator:
    """Drives all 9 simulation engines in a coordinated tick loop."""

    def __init__(self) -> None:
        self._market    = get_synthetic_market_engine()
        self._arena     = get_adversarial_arena()
        self._reflexive = get_reflexive_engine()
        self._liquidity = get_liquidity_warfare_engine()
        self._crowd     = get_crowd_psychology_engine()
        self._vol       = get_volatility_cascade_engine()
        self._macro     = get_macro_stress_engine()
        self._exchange  = get_exchange_failure_engine()
        self._latency   = get_latency_warfare_engine()

        self._tick_count = 0
        self._running    = False
        self._thread: threading.Thread | None = None
        self._lock       = threading.Lock()

    # ------------------------------------------------------------------
    def tick(self, ts_ns: int | None = None) -> None:
        """Single coordinated tick across all 9 engines with cross-signal routing."""
        if ts_ns is None:
            ts_ns = time.time_ns()

        try:
            with self._lock:
                self._tick_count += 1

            # 1. Market tick — generates price return + realised vol
            self._market.tick(ts_ns)
            mkt_snap     = self._market.snapshot()
            price_return = mkt_snap.get("last_log_return", 0.0)
            realised_vol = mkt_snap.get("realised_vol", 0.02)

            # 2. Macro stress — affects vol and prices
            self._macro.tick(ts_ns)
            macro_snap   = self._macro.snapshot()
            vol_mult     = macro_snap.get("composite_vol_mult", 1.0)
            stressed_vol = realised_vol * vol_mult

            # 3. Volatility cascade — fed stressed vol
            self._vol.tick(ts_ns, realised_vol=stressed_vol, price_return=price_return)
            vol_snap     = self._vol.snapshot()
            current_vol  = vol_snap.get("current_vol", stressed_vol)

            # 4. Crowd psychology — driven by price return + vol
            self._crowd.tick(ts_ns, price_return=price_return, market_vol=current_vol)

            # 5. Reflexive simulation — driven by price return
            self._reflexive.tick(ts_ns, price_return=price_return)

            # 6. Exchange failure
            self._exchange.tick(ts_ns)
            exc_snap    = self._exchange.snapshot()
            fill_rate   = exc_snap.get("aggregate_fill_rate", 1.0)

            # 7. Liquidity warfare — vol-driven attack rates
            self._liquidity.tick(ts_ns, market_vol=current_vol)

            # 8. Latency warfare — activity = inverse of fill_rate (stress proxy)
            market_activity = max(0.5, 1.0 + (1.0 - fill_rate) * 3.0)
            if current_vol > 0.04:
                market_activity *= 1.5
            self._latency.tick(ts_ns, market_activity=market_activity)

            # 9. Adversarial arena — driven by vol
            self._arena.tick(ts_ns, market_vol=current_vol)

        except Exception:
            pass

    def combined_snapshot(self) -> dict[str, Any]:
        """Merged snapshot from all 9 engines plus orchestrator metadata."""
        try:
            with self._lock:
                tick_count = self._tick_count

            return {
                "orchestrator": {
                    "tick_count": tick_count,
                    "engines":    9,
                    "running":    self._running,
                },
                "synthetic_market":   self._market.snapshot(),
                "adversarial_arena":  self._arena.snapshot(),
                "reflexive":          self._reflexive.snapshot(),
                "liquidity_warfare":  self._liquidity.snapshot(),
                "crowd_psychology":   self._crowd.snapshot(),
                "volatility_cascade": self._vol.snapshot(),
                "macro_stress":       self._macro.snapshot(),
                "exchange_failure":   self._exchange.snapshot(),
                "latency_warfare":    self._latency.snapshot(),
            }
        except Exception:
            return {"error": "snapshot_failed"}

    # ------------------------------------------------------------------
    # Background loop (used when wired into the simulation runtime)
    # ------------------------------------------------------------------
    def start(self, tick_interval_s: float = 0.1) -> None:
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(
            target=self._loop, args=(tick_interval_s,), daemon=True, name="stage8-orch",
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _loop(self, interval: float) -> None:
        while self._running:
            self.tick()
            time.sleep(interval)

    # Macro scenario injection (operator API)
    def activate_macro_scenario(self, name: str) -> bool:
        return self._macro.activate_scenario(name, time.time_ns())


# ── Singleton ──────────────────────────────────────────────────────────────────

_singleton: Stage8SimulationOrchestrator | None = None
_lock = threading.Lock()


def get_stage8_orchestrator() -> Stage8SimulationOrchestrator:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = Stage8SimulationOrchestrator()
    return _singleton


__all__ = ["Stage8SimulationOrchestrator", "get_stage8_orchestrator"]

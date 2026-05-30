"""ui.simulation_routes — Stage 8 Simulation Dominance REST endpoints.

12 read-only endpoints under /api/simulation/*:

  GET /api/simulation/snapshot          — combined all-engine snapshot
  GET /api/simulation/market            — synthetic market (GBM+Heston+Merton)
  GET /api/simulation/arena             — adversarial trader arena
  GET /api/simulation/reflexive         — Soros reflexivity engine
  GET /api/simulation/liquidity         — liquidity warfare (spoofing/layering)
  GET /api/simulation/crowd             — crowd psychology (sentiment machine)
  GET /api/simulation/volatility        — volatility cascade (regimes, gamma)
  GET /api/simulation/macro             — macro stress (9 scenarios)
  GET /api/simulation/exchange          — exchange failure (5 venues)
  GET /api/simulation/latency           — latency warfare (4 tiers)
  POST /api/simulation/macro/activate   — operator: activate named macro scenario
  POST /api/simulation/tick             — advance all engines by one tick (testing)

PAPER ONLY / RESEARCH ONLY / LEARNING ONLY / SIMULATION ONLY.
Real capital deployment is permanently disabled.
"""
from __future__ import annotations

from system.time_source import wall_ns
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from simulation.stage8_orchestrator import get_stage8_orchestrator


def build_simulation_router() -> APIRouter:
    router = APIRouter(prefix="/api/simulation", tags=["simulation"])
    orch   = get_stage8_orchestrator()

    @router.get("/snapshot")
    async def simulation_snapshot() -> dict[str, Any]:
        """Combined snapshot from all 9 simulation engines."""
        return orch.combined_snapshot()

    @router.get("/market")
    async def simulation_market() -> dict[str, Any]:
        """Synthetic market engine snapshot (GBM + Heston + Merton)."""
        from simulation.engines.synthetic_market import get_synthetic_market_engine
        return get_synthetic_market_engine().snapshot()

    @router.get("/arena")
    async def simulation_arena() -> dict[str, Any]:
        """Adversarial trader arena snapshot (5 agent archetypes)."""
        from simulation.engines.adversarial_arena import get_adversarial_arena
        return get_adversarial_arena().snapshot()

    @router.get("/reflexive")
    async def simulation_reflexive() -> dict[str, Any]:
        """Reflexive simulation engine snapshot (Soros reflexivity)."""
        from simulation.engines.reflexive import get_reflexive_engine
        return get_reflexive_engine().snapshot()

    @router.get("/liquidity")
    async def simulation_liquidity() -> dict[str, Any]:
        """Liquidity warfare engine snapshot (spoofing, layering, depth erosion)."""
        from simulation.engines.liquidity_warfare import get_liquidity_warfare_engine
        return get_liquidity_warfare_engine().snapshot()

    @router.get("/crowd")
    async def simulation_crowd() -> dict[str, Any]:
        """Crowd psychology engine snapshot (7-state sentiment machine)."""
        from simulation.engines.crowd_psychology import get_crowd_psychology_engine
        return get_crowd_psychology_engine().snapshot()

    @router.get("/volatility")
    async def simulation_volatility() -> dict[str, Any]:
        """Volatility cascade engine snapshot (regime, gamma squeeze, contagion)."""
        from simulation.engines.volatility_cascade import get_volatility_cascade_engine
        return get_volatility_cascade_engine().snapshot()

    @router.get("/macro")
    async def simulation_macro() -> dict[str, Any]:
        """Macro stress engine snapshot (9 scenarios, composite stress index)."""
        from simulation.engines.macro_stress import get_macro_stress_engine
        return get_macro_stress_engine().snapshot()

    @router.get("/exchange")
    async def simulation_exchange() -> dict[str, Any]:
        """Exchange failure engine snapshot (5 venues, multi-state failure/recovery)."""
        from simulation.engines.exchange_failure import get_exchange_failure_engine
        return get_exchange_failure_engine().snapshot()

    @router.get("/latency")
    async def simulation_latency() -> dict[str, Any]:
        """Latency warfare engine snapshot (4 tiers, queue position, adverse selection)."""
        from simulation.engines.latency_warfare import get_latency_warfare_engine
        return get_latency_warfare_engine().snapshot()

    class MacroActivateRequest(BaseModel):
        scenario: str

    @router.post("/macro/activate")
    async def simulation_macro_activate(body: MacroActivateRequest) -> dict[str, Any]:
        """Operator injection: activate a named macro stress scenario."""
        ok = orch.activate_macro_scenario(body.scenario)
        if not ok:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown macro scenario: {body.scenario!r}",
            )
        return {"activated": body.scenario, "ts_ns": wall_ns()}

    @router.post("/tick")
    async def simulation_tick() -> dict[str, Any]:
        """Advance all 9 engines by one tick. For testing/dev use only."""
        orch.tick()
        return {"ticked": True, "ts_ns": wall_ns()}

    return router

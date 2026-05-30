"""simulation.engines — Stage 8 simulation engine modules.

Nine specialist engines, each self-contained with tick() + snapshot():
  synthetic_market    — GBM + Heston vol + Merton jump diffusion
  adversarial_arena   — 5 adversarial agent types running in tournament
  reflexive           — Soros reflexivity + momentum cascade detection
  liquidity_warfare   — spoofing, layering, market-depth erosion
  crowd_psychology    — 7-state sentiment machine + herding + contagion
  volatility_cascade  — vol regime transitions + gamma squeeze + contagion
  macro_stress        — 9 macro scenario catalog with composite stress index
  exchange_failure    — multi-venue failure modes + circuit breakers
  latency_warfare     — 4 latency tiers, queue-position model, adverse selection
"""

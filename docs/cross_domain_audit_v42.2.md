# Cross-Domain Audit — v42.2 Cognitive Expansion (§5)

**Date:** 2026-05-31  
**Authority:** `docs/manifest_v42.2_cognitive_expansion.md` §5

---

## Allowed pathways

| Path | Implementation | Status |
|------|----------------|--------|
| Dyon → Governance (hazard) | `execution/hazard/async_bus.py`, `governance/kernel.py`, `governance/hazard_router.py` | ✅ Compliant |
| Dyon/Risk → Governance → Indira (context) | `governance/market_context_projector.py` → `CognitiveChannel.GOVERNED_MARKET_CONTEXT` → `intelligence_engine/cognitive/dyon_signal_bridge.py` | ✅ Fixed |

---

## Remediated violations

| Violation | Before | After |
|-----------|--------|-------|
| Direct SYSTEM→MARKET bus subscribe | `DyonSignalBridge` subscribed to `DYON_SCAN_COMPLETE`, `DYON_PROPOSAL`, `RISK_BREACH` | Bridge subscribes only to `GOVERNED_MARKET_CONTEXT` |
| Governance bypass for learning feedback | Dyon events translated in Indira domain | `MarketContextProjector` validates and publishes governed payloads |

---

## Reviewed — compliant or out of scope

| Path | Verdict |
|------|---------|
| Indira → ExecutionIntent → governance gate → execution | Allowed (MARKET → AUTHORITY → ACTION) |
| `intelligence_engine/cognitive/dyon_signal_bridge` name | Legacy alias retained; behavior is governed-context only |
| Contracts / protos (`SYSTEM_HAZARD` in `contracts/`) | Typed cross-domain per INV-08 |
| `core/authority.py` domain decorators | Enforcement layer; not a covert crossover |
| Neuromorphic anomaly → Dyon → SYSTEM_HAZARD | Compliant per `docs/NEUROMORPHIC_TRIAD_SPEC.md` |

---

## Ongoing watchlist

| Area | Note |
|------|------|
| `tools/authority_lint.py` | Run in CI to catch new B1 import violations |
| Charter imports in `cockpit/chat.py` | Voice routing only; no execution crossover |
| Simulation → `GovernedEvolutionPipeline` | CLASS_A proposals; evolution domain only |

---

## Operator action

Set `DIX_AUTHORITY_STRICT=1` in production. Any new Indira↔Dyon coupling must add a row to the allowed-pathways table above and a governance projector — never a direct bus subscription.

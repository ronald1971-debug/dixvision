# Manifest Delta — Cognitive Expansion vs Janus-Interrupt Lock

**From:** `DIX VISION v42.2 – CANONICAL SYSTEM MANIFEST.txt` (execution-centric lock)  
**To:** `docs/manifest_v42.2_cognitive_expansion.md` (AoR)

---

## Preserved (no regression)

| Item | Notes |
|------|--------|
| INDIRA fast path | Still execution-adjacent; intents on market hot path with precomputed governance constraints |
| SYSTEM_HAZARD | Dyon → Governance only; Lean axioms unchanged |
| Ledger / replay / INV-15 | Append-only hash chain, deterministic replay |
| Promotion gates | SHADOW → CANARY → LIVE hash-bound criteria |
| Dual charters | `intelligence_engine/charter/indira.py`, `evolution_engine/charter/dyon.py` |

---

## Changed

| Topic | Old lock | Cognitive Expansion |
|-------|----------|---------------------|
| Primary product | Production trading platform | Governed intelligence OS; trading downstream |
| §0 INDIRA label | "Trade Execution Authority" (implies sole executor) | **Execution-adjacent** market cognition; Execution Layer enforces |
| Tier model | Implicit dual-domain | Explicit Tier 0–4 (Operator → … → Capital) |
| Cross-domain | "Shared knowledge ≠ shared authority" only | Two governed channels: `SYSTEM_HAZARD`, `GOVERNED_MARKET_CONTEXT` |
| Runtime priority | Fast path first in narrative | Cognitive development pipeline ≥ trading pipeline |
| Dyon→Indira coupling | `DyonSignalBridge` on raw Dyon bus | **Removed** — `governance/market_context_projector.py` + governed channel |

---

## Added (code + docs)

| Artifact | Purpose |
|----------|---------|
| `docs/manifest_v42.2_cognitive_expansion.md` | AoR |
| `docs/cross_domain_audit_v42.2.md` | §5 enforcement record |
| `governance/market_context_projector.py` | Dyon/Risk → Governance → Indira |
| `intelligence_engine/cognitive/cognitive_development_pipeline.py` | §6 FSM |
| `cognitive_governance/cognitive_maturity.py` | §7 stage registry |
| `tests/test_cognitive_development.py` | Pipeline + maturity tests |

---

## INDIRA execution-adjacent (explicit reconciliation)

The old manifest stated INDIRA executes trades directly. The Cognitive Expansion AoR refines this:

- INDIRA **owns intent formation** and sits **adjacent** to execution on the hot path.
- **ExecutionEngine** and adapters perform ACTION; governance supplies precomputed constraints.
- INDIRA must not be demoted to a offline analyst — market ticks, meta-controller, and intent producer remain on the spine's Phase 3 cadence.

This is a **wording and authority-boundary** correction, not removal of the fast path.

# BUILD DIRECTIVE — Lint Rule ID Mapping

The MERGED BUILD DIRECTIVE references lint rules B30–B34 for new enforcement.
However, B30–B33 already existed in `tools/authority_lint.py` with different
semantics (predating the directive). This document maps directive rule IDs
to their implemented names.

| Directive ID | Implemented As | Semantics |
|---|---|---|
| B30 (new) | **B-FETCH** | External adapters expose only `fetch_*` methods |
| B31 (new) | **B-OPAUTH** | Only `OperatorInterfaceBridge` writes `operator_authority` |
| B32 (new) | **B-COMPOSER** | Only `strategy_composer/composer.py` constructs `ComposedStrategy` |
| B33 (new) | **B-CLOCK** ✓ | Already existed — bans `time.time*`/`datetime.now*` outside `system/time_source.py` |
| B34 (new) | **B-MANUAL** | Only dashboard order-ticket produces `ExecutionIntent` in MANUAL mode |

## Pre-existing rules (unchanged)

| Rule ID | Semantics (pre-directive) |
|---|---|
| B30 | Unify-Intelligence-into-BeliefState (reviewer #3 v3 §2) |
| B31 | Mode-effect table is the single mode-conditional oracle |
| B32 | Mode FSM single mutator (P0-6, INV-mode-fsm) |
| B33 | No-implicit-approval (Hardening-S1 item 1) |
| B35 | AI-domain operator-directive restriction (Hardening-S1 item 7) |
| B36 | DecisionSigner construction restriction (Hardening-S1 item 2) |
| B-CLOCK | Raw clock chokepoint (P0-1a, INV-15) — same as directive B33 |
| B-TORCH | Torch containment (I-36, INV-15) |
| B-POLARS | Polars containment (S-10.4, INV-15) |

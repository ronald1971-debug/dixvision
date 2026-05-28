# DIX VISION v42.2

Autonomous trading system — Janus-Sentinel architecture.

## Architecture

Six runtime engines with strict domain isolation (INV-08/INV-11):

| Engine | Domain | Path |
|---|---|---|
| **Intelligence** | Signal generation, meta-controller, microstructure plugins | `intelligence_engine/` |
| **Execution** | Order routing, authority gate, fill reconciliation | `execution_engine/` |
| **Governance** | Mode FSM, policy engine, operator consent, HMAC signing | `governance_engine/` |
| **System** | HAZ sensors, hazard bus, system heartbeat | `system_engine/` |
| **Learning** | Closed-loop strategy feedback (offline) | `learning_engine/` |
| **Evolution** | Structural mutation, patch pipeline (offline) | `evolution_engine/` |

Two operator UIs:
- **Operator Dashboard** — `dashboard2026/` (React 19 + Vite)
- **Memecoin Dashboard** — `dash_meme/` (React + Vite, DEX-oriented)

Safety primitives:
- 72 invariants (INV-01..72) + 69 safety axioms (SAFE-01..69) in `immutable_core/axioms.py`
- Kill switch: stdlib-only `os._exit(1)` in `immutable_core/kill_switch.py`
- Execution gate: HMAC + actor matrix + dev-mode policy + hazard throttle
- `live_execution: BLOCKED` by default — operator consent required for live trading

## Prerequisites

- Python 3.11+
- Node 20+ (for frontend builds)
- pip

## Quick Start (bare Python)

```bash
# Clone
git clone https://github.com/your-org/dix-vision.git
cd dix-vision

# Install base dependencies
pip install -e .

# Optional: install extras for specific features
pip install -e ".[neuromorphic]"   # torch / snntorch / bindsnet / brian2
pip install -e ".[ml]"             # jax / nengo / tianshou
pip install -e ".[causal]"         # causalml / dowhy / econml

# Build the operator dashboard (requires Node 20+)
cd dashboard2026 && npm install && npm run build && cd ..

# Build the memecoin dashboard (optional)
cd dash_meme && npm install && npm run build && cd ..

# Verify installation
python dix.py verify

# Start the full system
python start.py
```

The server starts at `http://127.0.0.1:8080/`. The operator dashboard
is at `/dash2/`, the memecoin dashboard at `/meme/`.

## Quick Start (Docker)

```bash
docker build -t dix-vision:42.2 .
docker run --rm -p 8765:8765 -v dix-data:/data dix-vision:42.2
```

> **Note:** Docker runs the **cockpit** by default (lightweight pairing +
> worker surface). For the full trading system with all 6 engines:
>
> ```bash
> docker run --rm -p 8080:8080 -v dix-data:/data dix-vision:42.2 python start.py
> ```

## First-Time Operator Setup

1. Start in **PAPER** mode (default) — no real money at risk.
2. Add API credentials via the `/dash2/#/credentials` page or set env vars.
3. Run `python dix.py verify` to confirm all engines boot correctly.
4. Promotion from PAPER → LIVE requires explicit operator consent with TOTP.

## Key Commands

```bash
python dix.py verify         # Boot verification (all engines)
python dix.py status         # Current system status
python dix.py ledger check   # Audit ledger integrity
python main.py --verify      # Full startup verification
```

## Cloud Deployment

See [docs/CLOUD.md](docs/CLOUD.md) for Fly.io, Render, Railway, VPS,
and Kubernetes deployment guides.

## Installation Guide

See [docs/INSTALL.md](docs/INSTALL.md) for Windows portable exe,
cloud one-click deploy, and Python from-source installation.

## Documentation

- [Cognitive OS Architecture](docs/COGNITIVE_OS.md) — Kernel, signal funnel, compression model
- [Architecture](docs/ARCHITECTURE_V42_2_TIER0.md) — Tier-0 architecture spec
- [Cloud Deployment](docs/CLOUD.md) — Docker, Fly.io, Render, Railway, K8s
- [Installation](docs/INSTALL.md) — Windows, cloud, from-source
- [Neuromorphic Spec](docs/NEUROMORPHIC_TRIAD_SPEC.md) — SNN triad design
- [Memecoin Trading](docs/MEMECOIN_TRADING_SPEC.md) — DEX trading spec

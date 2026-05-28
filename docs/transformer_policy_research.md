# I-35 — Transformer Policy Research

**ADAPTED FROM:** https://github.com/facebookresearch/xformers + https://github.com/openai/triton  
**License:** BSD-3-Clause  
**Classification:** OFFLINE research only (GPU optional)

## Overview

Explores transformer-based policies that attend over orderbook sequences
to learn trading strategies via evolutionary search (evolution_engine).

## Architecture

```
Orderbook Snapshots (seq_len=128)
    ↓
Linear Projection (features → d_model=64)
    ↓
Multi-Head Self-Attention (4 heads, memory-efficient via xformers)
    ↓
Feed-Forward (d_model → action_dim=3)
    ↓
Action Logits: [BUY, HOLD, SELL]
```

## Why xformers

Standard self-attention is O(n²) in memory for sequence length n.
For orderbook sequences of 128+ snapshots, xformers'
`memory_efficient_attention` reduces this to O(n) memory via
chunked computation — critical for batch evolution with large populations.

## Why Triton

Custom GPU kernels via Triton enable fused operations
(attention + layer norm + dropout in one kernel pass), reducing
memory bandwidth bottleneck on GPU.

## Integration with DIX

- **evolution_engine/jax_policy_search.py** (I-34): JAX for fast
  batch evaluation; transformer policy as one candidate architecture.
- **evolution_engine/sandbox.py** (A-01): SB3 environments provide
  the fitness function for policy search.
- **simulation/adversarial/jax_lob_sim.py** (C-46): Realistic
  orderbook data for training sequences.

## Research Questions

1. Does attention over orderbook history outperform fixed-window features?
2. What sequence length gives best risk-adjusted return?
3. Can learned attention patterns reveal interpretable market structure?

## GPU Requirements

- CUDA 11.8+ for xformers
- NVIDIA GPU with ≥8GB VRAM (RTX 3080+)
- CI runs in mock mode (no GPU) — GPU tests are manual

## Usage

```python
from evolution_engine.experimental.transformer_policy import (
    TransformerPolicy,
    TransformerConfig,
)

config = TransformerConfig(seq_len=128, d_model=64, n_heads=4)
policy = TransformerPolicy(config=config, in_memory=False)

# Forward pass over orderbook sequence
output = policy.forward(orderbook_snapshots)
print(output.action_logits)  # (buy_logit, hold_logit, sell_logit)
```

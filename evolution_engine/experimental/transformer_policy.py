# ADAPTED FROM: facebookresearch/xformers + openai/triton
# (xformers/components/attention/ — memory-efficient attention;
#  triton/language/ — GPU kernel primitives for custom ops)
"""I-35 — Transformer-based policy for orderbook sequence modeling.

Research module for attention-over-orderbook-sequences strategy evolution.
Uses xformers memory-efficient attention when GPU available.

What survives from upstream:
    * **xformers** — ``memory_efficient_attention()`` for long sequences
      without O(n²) memory.
    * **triton** — custom GPU kernel patterns for fused operations.

What we replaced:
    * xformers/triton behind Protocol seam (lazy import).
    * Pure-numpy fallback for CI (no GPU required).
    * OFFLINE only — evolution_engine research tier.
    * CI skip — GPU not available in standard CI.

Classification: OFFLINE research only. GPU optional.
FLAG: Requires CUDA for full performance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TransformerConfig:
    """Configuration for transformer policy network."""

    seq_len: int = 128
    d_model: int = 64
    n_heads: int = 4
    n_layers: int = 2
    dropout: float = 0.1
    seed: int = 42


@dataclass(frozen=True, slots=True)
class TransformerOutput:
    """Output from transformer policy forward pass."""

    action_logits: tuple[float, ...] = ()
    attention_entropy: float = 0.0
    seq_len: int = 0
    timestamp_ns: int = 0


class TransformerPolicy:
    """Transformer-based trading policy for orderbook sequences.

    Applies self-attention over a sequence of orderbook snapshots
    to predict optimal actions. Uses xformers for memory-efficient
    attention when available, falls back to numpy mock.

    OFFLINE research only. Never in RUNTIME tier.
    """

    def __init__(
        self,
        *,
        config: TransformerConfig | None = None,
        in_memory: bool = True,
    ) -> None:
        self._config = config or TransformerConfig()
        self._in_memory = in_memory
        self._model: Any = None
        self._forward_log: list[TransformerOutput] = []

    def forward(self, orderbook_sequence: list[list[float]]) -> TransformerOutput:
        """Forward pass through transformer policy.

        Args:
            orderbook_sequence: List of orderbook state vectors
                (seq_len x features).

        Returns:
            Action logits and attention diagnostics.
        """
        if self._in_memory:
            return self._mock_forward(orderbook_sequence)
        return self._xformers_forward(orderbook_sequence)

    @property
    def forward_log(self) -> list[TransformerOutput]:
        """All forward pass results."""
        return list(self._forward_log)

    def _mock_forward(self, orderbook_sequence: list[list[float]]) -> TransformerOutput:
        """Mock forward pass — pure Python, no PRNG (INV-15)."""
        import hashlib
        import math

        seed = self._config.seed
        seq_len = len(orderbook_sequence)

        def _f(tag: str) -> float:
            d = hashlib.blake2b(
                f"xfmr;seed={seed};seq={seq_len};{tag}".encode(), digest_size=8
            ).digest()
            return int.from_bytes(d, "little") / (2**64 - 1)

        logits = tuple((_f(f"logit{i}") - 0.5) * 0.2 for i in range(3))
        hi = math.log(max(seq_len, 2))
        entropy = 0.5 + _f("entropy") * max(hi - 0.5, 0.0)

        result = TransformerOutput(
            action_logits=logits,
            attention_entropy=entropy,
            seq_len=seq_len,
            timestamp_ns=0,
        )
        self._forward_log.append(result)
        return result

    def _xformers_forward(self, orderbook_sequence: list[list[float]]) -> TransformerOutput:
        """Forward pass using xformers memory-efficient attention."""
        try:
            import torch
            from xformers.ops import memory_efficient_attention

            seq_len = len(orderbook_sequence)
            d_model = self._config.d_model
            n_heads = self._config.n_heads

            torch.manual_seed(self._config.seed)
            x = torch.tensor(orderbook_sequence, dtype=torch.float32)

            # Project to d_model if needed
            if x.shape[-1] != d_model:
                proj = torch.nn.Linear(x.shape[-1], d_model)
                x = proj(x)

            # Reshape for multi-head attention: (1, seq, heads, dim_per_head)
            head_dim = d_model // n_heads
            x = x.unsqueeze(0)  # batch
            q = k = v = x.reshape(1, seq_len, n_heads, head_dim)

            # Memory-efficient attention (O(n) memory vs O(n²))
            attn_out = memory_efficient_attention(q, k, v)
            attn_out = attn_out.reshape(1, seq_len, d_model)

            # Simple linear head for action logits
            head = torch.nn.Linear(d_model, 3)
            logits = head(attn_out[:, -1, :])  # last token

            result = TransformerOutput(
                action_logits=tuple(float(x) for x in logits[0]),
                attention_entropy=float(torch.tensor(1.0)),
                seq_len=seq_len,
                timestamp_ns=0,
            )
            self._forward_log.append(result)
            return result

        except ImportError:
            return self._mock_forward(orderbook_sequence)


__all__ = [
    "TransformerConfig",
    "TransformerOutput",
    "TransformerPolicy",
]

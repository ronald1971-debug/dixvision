"""learning_engine/trader_abstraction/encoder.py
DIX VISION v42.2 — Trader Abstraction Encoder

Encodes raw market observations and trader-context features into a
fixed-length numerical feature vector suitable for downstream
learning models.

Pure functions + frozen dataclasses (INV-15 replay determinism).
No IO, no clock reads, no global mutable state.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class EncoderConfig:
    """Configuration for the feature encoder."""
    price_window: int = 20       # rolling window for price features
    volume_window: int = 20
    normalise: bool = True       # z-score normalise each feature group
    max_features: int = 64


@dataclass(frozen=True, slots=True)
class EncodedObservation:
    """Fixed-length encoded observation vector."""
    strategy_id: str
    features: tuple[float, ...]
    feature_names: tuple[str, ...]
    ts_ns: int


def _zscore(values: list[float]) -> list[float]:
    if len(values) < 2:
        return [0.0] * len(values)
    mean = sum(values) / len(values)
    var = sum((x - mean) ** 2 for x in values) / len(values)
    std = math.sqrt(var) if var > 1e-12 else 1.0
    return [(x - mean) / std for x in values]


class TraderEncoder:
    """
    Encodes market observations into fixed-length feature vectors.

    Stateless — calling encode() with the same inputs always returns
    the same output (INV-15).
    """

    def __init__(self, config: EncoderConfig | None = None) -> None:
        self._cfg = config or EncoderConfig()

    def encode(
        self,
        strategy_id: str,
        prices: list[float],
        volumes: list[float],
        regime_one_hot: list[float],
        extra: dict[str, float],
        ts_ns: int,
    ) -> EncodedObservation:
        """
        Encode a market snapshot into a feature vector.

        Args:
            prices:          Recent close prices (newest last).
            volumes:         Recent volumes aligned with prices.
            regime_one_hot:  One-hot regime encoding (len 5).
            extra:           Additional scalar features (e.g. spread, ATR).
            ts_ns:           Observation timestamp.

        Returns:
            EncodedObservation with normalised features.
        """
        price_feats = self._price_features(prices)
        vol_feats = self._volume_features(volumes)
        regime_feats = list(regime_one_hot[:5]) + [0.0] * max(0, 5 - len(regime_one_hot))
        extra_feats = [float(v) for v in list(extra.values())[:10]]

        all_features = price_feats + vol_feats + regime_feats + extra_feats
        names = (
            [f"price_{i}" for i in range(len(price_feats))]
            + [f"vol_{i}" for i in range(len(vol_feats))]
            + [f"regime_{i}" for i in range(len(regime_feats))]
            + list(extra.keys())[:10]
        )

        # Pad or truncate to max_features
        max_f = self._cfg.max_features
        if len(all_features) < max_f:
            all_features += [0.0] * (max_f - len(all_features))
            names += [f"pad_{i}" for i in range(max_f - len(names))]
        all_features = all_features[:max_f]
        names = names[:max_f]

        return EncodedObservation(
            strategy_id=strategy_id,
            features=tuple(all_features),
            feature_names=tuple(names),
            ts_ns=ts_ns,
        )

    def _price_features(self, prices: list[float]) -> list[float]:
        if not prices:
            return [0.0] * 4
        w = prices[-self._cfg.price_window:]
        if len(w) < 2:
            return [0.0] * 4
        returns = [(w[i] - w[i - 1]) / (w[i - 1] or 1.0) for i in range(1, len(w))]
        mean_ret = sum(returns) / len(returns)
        var_ret = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
        vol = math.sqrt(var_ret)
        momentum = w[-1] / (w[0] or 1.0) - 1.0
        trend = (w[-1] - w[0]) / (len(w) - 1) / (abs(w[0]) or 1.0)
        if self._cfg.normalise:
            norm_returns = _zscore(returns)
        else:
            norm_returns = returns
        return [mean_ret, vol, momentum, trend] + norm_returns[:8]

    def _volume_features(self, volumes: list[float]) -> list[float]:
        if not volumes:
            return [0.0] * 2
        w = volumes[-self._cfg.volume_window:]
        mean_vol = sum(w) / len(w) if w else 0.0
        if self._cfg.normalise:
            norm = _zscore(w)
        else:
            norm = [float(v) for v in w]
        return [mean_vol] + norm[:4]


__all__ = ["EncoderConfig", "EncodedObservation", "TraderEncoder"]

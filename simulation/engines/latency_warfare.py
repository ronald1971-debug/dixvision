"""simulation.engines.latency_warfare — Latency Warfare Engine (Stage 8).

Models co-location arms race and adverse selection from latency disadvantage:

  Tiers (fastest to slowest):
    CO_LOCATED    — on-exchange rack; sub-100µs round-trip
    HFT           — proximity hosting; 100µs–1ms
    INSTITUTIONAL — dedicated fiber; 1ms–10ms
    RETAIL        — internet; 10ms–500ms

  Queue position: lower latency → earlier in queue → better fill priority
  Adverse selection: slower tiers filled on adverse price moves more often
  Fill probability: decays with latency relative to best-tier benchmark
  Queue drift: position worsens with market activity; improves with quiet

Latency index (0–100): 100 = co-located parity; 0 = worst retail lag.
"""
from __future__ import annotations

import dataclasses
import math
import random
import threading
from collections import deque
from typing import Any

_TIERS = ["CO_LOCATED", "HFT", "INSTITUTIONAL", "RETAIL"]

_TIER_PROPS: dict[str, dict] = {
    "CO_LOCATED":  {"latency_us": 80,     "queue_priority": 1.00, "base_fill_prob": 0.98},
    "HFT":         {"latency_us": 500,    "queue_priority": 0.82, "base_fill_prob": 0.91},
    "INSTITUTIONAL":{"latency_us": 5_000, "queue_priority": 0.55, "base_fill_prob": 0.78},
    "RETAIL":      {"latency_us": 80_000, "queue_priority": 0.15, "base_fill_prob": 0.55},
}

# Adverse selection: fraction of fills at adversely moved price, by tier
_ADVERSE_SELECTION: dict[str, float] = {
    "CO_LOCATED":   0.04,
    "HFT":          0.12,
    "INSTITUTIONAL":0.25,
    "RETAIL":       0.42,
}


@dataclasses.dataclass(frozen=True, slots=True)
class LatencyEvent:
    ts_ns:       int
    kind:        str    # QUEUE_JUMP | ADVERSE_FILL | LATENCY_SPIKE | TIER_CONTENTION
    tier:        str
    latency_us:  float
    fill_prob:   float
    adverse_sel: float


@dataclasses.dataclass(frozen=True, slots=True)
class TierSnapshot:
    tier:           str
    latency_us:     float
    queue_priority: float
    fill_prob:      float
    adverse_sel:    float
    queue_position: int    # estimated position in matching queue


class LatencyWarfareEngine:
    """Co-location arms race model with adverse selection and queue dynamics."""

    def __init__(self, seed: int = 91) -> None:
        self._rng             = random.Random(seed)
        self._latency_index   = 75.0          # 0–100; starts near co-lo parity mid-point
        self._queue_positions: dict[str, int] = {t: i * 10 + 1 for i, t in enumerate(_TIERS)}
        self._latency_spikes: dict[str, float] = {t: 0.0 for t in _TIERS}
        self._adverse_fills   = 0
        self._queue_jumps     = 0
        self._spike_count     = 0
        self._tick_count      = 0
        self._events: deque[LatencyEvent]   = deque(maxlen=200)
        self._index_history: deque[float]   = deque(maxlen=200)
        self._lock            = threading.Lock()

    # ------------------------------------------------------------------
    def tick(self, ts_ns: int, market_activity: float = 1.0) -> None:
        """market_activity: 1.0 = normal; >1 = busy (worsens queue positions)."""
        try:
            with self._lock:
                self._tick_count += 1

                # Latency index: drifts toward 50 with noise; activity degrades it
                drift = -market_activity * 0.5 + self._rng.gauss(0.2, 0.3)
                self._latency_index = max(0.0, min(100.0, self._latency_index + drift))
                self._index_history.append(round(self._latency_index, 2))

                for tier in _TIERS:
                    props = _TIER_PROPS[tier]

                    # Queue position degrades with activity, recovers in quiet
                    activity_penalty = int(market_activity * 3 * self._rng.random())
                    recovery         = max(0, int(self._rng.gauss(1.5, 0.5)))
                    self._queue_positions[tier] = max(
                        1,
                        self._queue_positions[tier] + activity_penalty - recovery,
                    )

                    # Latency spike: random burst from network congestion
                    if self._rng.random() < 0.03 * market_activity:
                        spike = self._rng.uniform(1.5, 8.0)
                        self._latency_spikes[tier] = props["latency_us"] * spike
                        self._spike_count += 1
                        self._events.append(LatencyEvent(
                            ts_ns      = ts_ns,
                            kind       = "LATENCY_SPIKE",
                            tier       = tier,
                            latency_us = round(self._latency_spikes[tier], 1),
                            fill_prob  = round(self._fill_prob(tier), 4),
                            adverse_sel= _ADVERSE_SELECTION[tier],
                        ))
                    else:
                        self._latency_spikes[tier] = max(
                            0.0, self._latency_spikes[tier] * 0.7
                        )

                    # Queue jump: faster tier leapfrogs slower one
                    if tier != "CO_LOCATED" and self._rng.random() < 0.08:
                        faster_tier = _TIERS[_TIERS.index(tier) - 1]
                        if self._queue_positions[faster_tier] < self._queue_positions[tier]:
                            self._queue_jumps += 1
                            self._events.append(LatencyEvent(
                                ts_ns      = ts_ns,
                                kind       = "QUEUE_JUMP",
                                tier       = faster_tier,
                                latency_us = round(
                                    _TIER_PROPS[faster_tier]["latency_us"], 1
                                ),
                                fill_prob  = round(self._fill_prob(faster_tier), 4),
                                adverse_sel= _ADVERSE_SELECTION[faster_tier],
                            ))

                    # Adverse fill: retail/institutional hit stale prices
                    adv_threshold = _ADVERSE_SELECTION[tier] * market_activity
                    if self._rng.random() < adv_threshold * 0.05:
                        self._adverse_fills += 1
                        self._events.append(LatencyEvent(
                            ts_ns      = ts_ns,
                            kind       = "ADVERSE_FILL",
                            tier       = tier,
                            latency_us = round(self._effective_latency(tier), 1),
                            fill_prob  = round(self._fill_prob(tier), 4),
                            adverse_sel= round(_ADVERSE_SELECTION[tier], 4),
                        ))
        except Exception:
            pass

    def _effective_latency(self, tier: str) -> float:
        base  = _TIER_PROPS[tier]["latency_us"]
        spike = self._latency_spikes.get(tier, 0.0)
        return base + spike

    def _fill_prob(self, tier: str) -> float:
        base    = _TIER_PROPS[tier]["base_fill_prob"]
        qp      = _TIER_PROPS[tier]["queue_priority"]
        q_pos   = self._queue_positions.get(tier, 1)
        q_penalty = min(0.30, (q_pos - 1) * 0.005)
        spike_factor = self._latency_spikes.get(tier, 0.0) / max(
            1.0, _TIER_PROPS[tier]["latency_us"]
        )
        spike_penalty = min(0.20, spike_factor * 0.05)
        return round(max(0.10, base * qp - q_penalty - spike_penalty), 4)

    def latency_index(self) -> float:
        return round(self._latency_index, 2)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            tier_list = [
                dataclasses.asdict(TierSnapshot(
                    tier           = tier,
                    latency_us     = round(self._effective_latency(tier), 1),
                    queue_priority = _TIER_PROPS[tier]["queue_priority"],
                    fill_prob      = self._fill_prob(tier),
                    adverse_sel    = _ADVERSE_SELECTION[tier],
                    queue_position = self._queue_positions[tier],
                ))
                for tier in _TIERS
            ]
            events = [dataclasses.asdict(e) for e in list(self._events)[-20:]]
            hist   = list(self._index_history)[-50:]
            return {
                "latency_index":    round(self._latency_index, 2),
                "adverse_fills":    self._adverse_fills,
                "queue_jumps":      self._queue_jumps,
                "spike_count":      self._spike_count,
                "tick_count":       self._tick_count,
                "tiers":            tier_list,
                "latency_history":  hist,
                "recent_events":    events,
            }


# ── Singleton ──────────────────────────────────────────────────────────────────

_singleton: LatencyWarfareEngine | None = None
_lock = threading.Lock()


def get_latency_warfare_engine() -> LatencyWarfareEngine:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = LatencyWarfareEngine()
    return _singleton


__all__ = ["LatencyWarfareEngine", "LatencyEvent", "TierSnapshot",
           "get_latency_warfare_engine"]

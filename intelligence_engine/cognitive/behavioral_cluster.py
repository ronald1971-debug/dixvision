"""intelligence_engine.cognitive.behavioral_cluster — BehavioralClusterTracker.

Groups live trader classifications from the trader_modeling pipeline and the
archetype arena into dynamic behavioral clusters.  Each cluster represents a
currently-active school of market participants (e.g. "7 momentum traders with
0.82 mean confidence").

Cluster state is driven by INDIRA_INSIGHT events from the event bus:
  - TraderModelingRuntime publishes per-classification insights
  - TraderIntelligenceRuntime publishes top-archetype-changed insights

The tracker maintains per-archetype clusters, computes cluster strength as an
exponential moving average of incoming confidence scores, and decays clusters
between observations.

Dominant cluster = highest (strength × log(size + 1)) composite score.
When the dominant cluster changes, an ARCHETYPE_EVOLUTION event is emitted.

Authority (B1): intelligence_engine.*, state.*, core.* only.
INV-15: ts_ns is caller-supplied; no wall-clock reads.
"""

from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass, field
from typing import Any

_logger = logging.getLogger(__name__)

# EMA alpha for cluster strength updates
_EMA_ALPHA: float = 0.25
# Decay applied to cluster strength each tick without evidence (per tick)
_DECAY_PER_TICK: float = 0.005
# Minimum strength before a cluster is considered dormant
_DORMANCY_THRESHOLD: float = 0.05


# ---------------------------------------------------------------------------
# Cluster record
# ---------------------------------------------------------------------------


@dataclass
class BehavioralCluster:
    """One live behavioral cluster grouped by trader archetype."""

    archetype: str          # e.g. "momentum_trader", "hft_scalper"
    size: int = 0           # cumulative observation count
    strength: float = 0.0   # EMA of incoming confidence scores
    last_observed_ns: int = 0
    ticks_dormant: int = 0
    is_dominant: bool = False
    feature_mean: dict[str, float] = field(default_factory=dict)  # optional centroid

    @property
    def composite_score(self) -> float:
        """Cluster ranking score — strength weighted by log-size."""
        return self.strength * math.log(self.size + 1) if self.size > 0 else 0.0

    def update(self, confidence: float, ts_ns: int, features: dict[str, float] | None = None) -> None:
        """Incorporate a new observation into this cluster."""
        self.size += 1
        # EMA strength update
        if self.strength == 0.0:
            self.strength = confidence
        else:
            self.strength = (1.0 - _EMA_ALPHA) * self.strength + _EMA_ALPHA * confidence
        self.strength = max(0.0, min(1.0, self.strength))
        self.last_observed_ns = ts_ns
        self.ticks_dormant = 0
        # Update feature centroid via EMA
        if features:
            for k, v in features.items():
                prev = self.feature_mean.get(k, v)
                self.feature_mean[k] = (1.0 - _EMA_ALPHA) * prev + _EMA_ALPHA * v

    def to_dict(self) -> dict[str, Any]:
        return {
            "archetype": self.archetype,
            "size": self.size,
            "strength": round(self.strength, 3),
            "composite_score": round(self.composite_score, 3),
            "is_dominant": self.is_dominant,
            "ticks_dormant": self.ticks_dormant,
            "last_observed_ns": self.last_observed_ns,
        }


# ---------------------------------------------------------------------------
# BehavioralClusterTracker
# ---------------------------------------------------------------------------


class BehavioralClusterTracker:
    """Tracks live behavioral clusters from incoming trader classifications.

    Subscribes to the INDIRA_INSIGHT event bus channel on activate().
    Insight payloads from TraderModelingRuntime carry an archetype label
    and confidence; these feed directly into cluster updates.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._clusters: dict[str, BehavioralCluster] = {}
        self._dominant: str = ""
        self._prev_dominant: str = ""
        self._tick_count: int = 0
        self._observation_count: int = 0
        self._activated: bool = False

    # ------------------------------------------------------------------
    # Activation
    # ------------------------------------------------------------------

    def activate(self) -> None:
        """Subscribe to INDIRA_INSIGHT event bus.  Idempotent."""
        with self._lock:
            if self._activated:
                return
            self._activated = True
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().subscribe(CognitiveChannel.INDIRA_INSIGHT, self._on_insight)
            _logger.info("BehavioralClusterTracker: subscribed to INDIRA_INSIGHT")
        except Exception as exc:
            _logger.debug("BehavioralClusterTracker: subscribe error: %s", exc)

    # ------------------------------------------------------------------
    # Primary API
    # ------------------------------------------------------------------

    def observe(
        self,
        archetype: str,
        confidence: float,
        ts_ns: int,
        features: dict[str, float] | None = None,
    ) -> None:
        """Directly observe a trader archetype classification."""
        if not archetype:
            return
        with self._lock:
            self._observation_count += 1
            if archetype not in self._clusters:
                self._clusters[archetype] = BehavioralCluster(archetype=archetype)
            self._clusters[archetype].update(confidence, ts_ns, features)

    def tick(self, ts_ns: int) -> bool:
        """Advance one cluster tick.

        - Decays dormant clusters.
        - Recomputes the dominant cluster.
        - Emits ARCHETYPE_EVOLUTION if dominant changed.

        Returns True if the dominant cluster changed this tick.
        """
        with self._lock:
            self._tick_count += 1
            # Decay all clusters
            for cl in self._clusters.values():
                cl.ticks_dormant += 1
                if cl.ticks_dormant > 1:
                    cl.strength = max(0.0, cl.strength - _DECAY_PER_TICK)
            # Recompute dominant
            active = {
                a: c for a, c in self._clusters.items()
                if c.strength >= _DORMANCY_THRESHOLD
            }
            prev = self._dominant
            if active:
                new_dom = max(active, key=lambda a: active[a].composite_score)
            else:
                new_dom = ""
            for cl in self._clusters.values():
                cl.is_dominant = (cl.archetype == new_dom)
            changed = (new_dom != prev)
            self._dominant = new_dom
            if changed:
                self._prev_dominant = prev
            # Snapshot for emit (outside lock)
            if changed and new_dom:
                dom_cl = self._clusters.get(new_dom)
                dom_snap = dom_cl.to_dict() if dom_cl else {}
            else:
                dom_snap = {}

        if changed and new_dom and dom_snap:
            self._emit_dominance_change(new_dom, dom_snap, ts_ns)

        return changed

    # ------------------------------------------------------------------
    # Read surface
    # ------------------------------------------------------------------

    def dominant_cluster(self) -> tuple[str, float]:
        """Return (archetype_name, strength) of the dominant cluster."""
        with self._lock:
            if not self._dominant:
                return ("", 0.0)
            cl = self._clusters.get(self._dominant)
            return (self._dominant, cl.strength if cl else 0.0)

    def format_for_context(self) -> str:
        """Compact cluster context string for ThoughtRuntime injection."""
        name, strength = self.dominant_cluster()
        if not name:
            return ""
        with self._lock:
            cl = self._clusters.get(name)
            size = cl.size if cl else 0
        return f"behavioral_cluster={name}({size}_members,{strength:.2f}_strength)"

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            clusters = [c.to_dict() for c in self._clusters.values()]
            clusters.sort(key=lambda c: -c["composite_score"])
            return {
                "runtime": "BehavioralClusterTracker",
                "tick_count": self._tick_count,
                "observation_count": self._observation_count,
                "cluster_count": len(self._clusters),
                "dominant": self._dominant,
                "prev_dominant": self._prev_dominant,
                "clusters": clusters,
            }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_insight(self, payload: dict[str, Any]) -> None:
        """Handle INDIRA_INSIGHT event — extract archetype signal if present."""
        subject = str(payload.get("subject", ""))
        ts_ns = int(payload.get("ts_ns", 0))
        if not ts_ns:
            return
        # TraderModelingRuntime publishes subject="TRADER_ARCHETYPE_OBSERVED"
        if subject == "TRADER_ARCHETYPE_OBSERVED":
            archetype = str(payload.get("archetype", ""))
            confidence = float(payload.get("confidence", 0.5))
            features: dict[str, float] = payload.get("features", {}) or {}
            self.observe(archetype, confidence, ts_ns, features)
        # TraderIntelligenceRuntime publishes subject="TOP_TRADER_ARCHETYPE"
        elif subject == "TOP_TRADER_ARCHETYPE":
            body = str(payload.get("body", ""))
            # Parse "Dominant archetype: <name> (win_rate=..., regime=...)"
            if "Dominant archetype:" in body:
                parts = body.split("Dominant archetype:", 1)
                archetype_part = parts[1].strip().split(" ")[0].strip("(,")
                if archetype_part:
                    confidence = float(payload.get("confidence", 0.65))
                    self.observe(archetype_part, confidence, ts_ns)

    def _emit_dominance_change(
        self,
        new_dominant: str,
        dom_snap: dict[str, Any],
        ts_ns: int,
    ) -> None:
        """Emit ARCHETYPE_EVOLUTION event when dominant cluster changes."""
        try:
            from intelligence_engine.cognitive.observability_emitter import (
                emit_archetype_evolution,
            )
            emit_archetype_evolution(
                ts_ns=ts_ns,
                archetype_id=new_dominant,
                archetype_name=new_dominant.replace("_", " ").title(),
                old_fitness=None,
                new_fitness=dom_snap.get("strength", 0.0),
                regime=self._current_regime(),
                evaluation_basis=f"behavioral_cluster_dominance size={dom_snap.get('size', 0)}",
            )
        except Exception:
            pass

    @staticmethod
    def _current_regime() -> str:
        try:
            from state.market_state import get_market_state
            return get_market_state().regime()
        except Exception:
            return "MIXED"


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_tracker: BehavioralClusterTracker | None = None
_tracker_lock = threading.Lock()


def get_behavioral_cluster_tracker() -> BehavioralClusterTracker:
    """Return the process-wide BehavioralClusterTracker singleton."""
    global _tracker
    with _tracker_lock:
        if _tracker is None:
            _tracker = BehavioralClusterTracker()
    return _tracker


__all__ = [
    "BehavioralCluster",
    "BehavioralClusterTracker",
    "get_behavioral_cluster_tracker",
]

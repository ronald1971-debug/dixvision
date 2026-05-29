"""runtime.unified_fabric.lineage — EventLineageGraph.

Tracks causal relationships between events: which event caused which.
Enables the operator to trace the root cause of any system state change.

Example chains the lineage graph can reveal:
  MARKET_TICK → INDIRA_THOUGHT → DYON_VIOLATION → GOVERNANCE_MODE_TRANSITION
  RISK_BREACH → INDIRA_CONFIDENCE_DROP → STRATEGY_MUTATION_BLOCKED

Graph structure:
- Node: event_id
- Edge: CausalLink (cause → effect, with kind label)
- In-memory with bounded deque; no persistence needed (tracer has spans)

Thread-safe. No clock reads (INV-15).
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict, deque
from typing import TYPE_CHECKING

from runtime.unified_fabric.contracts import CausalLink

if TYPE_CHECKING:
    pass

_logger   = logging.getLogger(__name__)
_MAX_LINKS = 10_000


class EventLineageGraph:
    """Directed graph of causal event links."""

    def __init__(self, max_links: int = _MAX_LINKS) -> None:
        self._max_links  = max_links
        self._lock       = threading.Lock()
        self._links:     deque[CausalLink] = deque(maxlen=max_links)
        # cause_id → list of effect CausalLinks
        self._forward:   dict[str, list[CausalLink]] = defaultdict(list)
        # effect_id → cause CausalLink
        self._backward:  dict[str, CausalLink]        = {}
        self._total:     int = 0

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record(self, link: CausalLink) -> None:
        """Store one causal link. Idempotent for same cause→effect pair."""
        try:
            key = f"{link.cause_id}>{link.effect_id}"
            with self._lock:
                if key in self._backward or link.effect_id in self._backward:
                    return   # already recorded
                self._links.append(link)
                self._forward[link.cause_id].append(link)
                self._backward[link.effect_id] = link
                self._total += 1
        except Exception as exc:
            _logger.debug("EventLineageGraph.record error: %s", exc)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def effects_of(self, cause_id: str) -> list[CausalLink]:
        """Return all direct effects caused by cause_id."""
        with self._lock:
            return list(self._forward.get(cause_id, []))

    def cause_of(self, effect_id: str) -> CausalLink | None:
        """Return the direct cause of effect_id, or None."""
        with self._lock:
            return self._backward.get(effect_id)

    def root_cause(self, event_id: str, max_depth: int = 20) -> list[str]:
        """Trace back to the root cause. Returns chain from root to event_id."""
        chain = [event_id]
        current = event_id
        depth = 0
        with self._lock:
            while depth < max_depth:
                link = self._backward.get(current)
                if link is None:
                    break
                chain.append(link.cause_id)
                current = link.cause_id
                depth += 1
        chain.reverse()
        return chain

    def causal_tree(self, root_id: str, max_depth: int = 5) -> dict:
        """Return a nested dict representing the causal tree from root_id."""
        def _expand(eid: str, depth: int) -> dict:
            if depth >= max_depth:
                return {"event_id": eid, "children": []}
            with self._lock:
                effects = list(self._forward.get(eid, []))
            return {
                "event_id": eid,
                "children": [
                    _expand(link.effect_id, depth + 1)
                    for link in effects
                ],
            }
        return _expand(root_id, 0)

    def recent_links(self, limit: int = 50) -> list[dict]:
        """Return most recent causal links."""
        with self._lock:
            links = list(self._links)
        links.sort(key=lambda l: l.ts_ns, reverse=True)
        return [
            {
                "cause_id":  l.cause_id,
                "effect_id": l.effect_id,
                "ts_ns":     l.ts_ns,
                "kind":      l.kind,
            }
            for l in links[:limit]
        ]

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "active":      True,
                "total_links": self._total,
                "ring_size":   len(self._links),
                "max_links":   self._max_links,
                "unique_causes": len(self._forward),
            }


_singleton: EventLineageGraph | None = None
_lock = threading.Lock()


def get_event_lineage_graph() -> EventLineageGraph:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = EventLineageGraph()
    return _singleton


__all__ = ["EventLineageGraph", "get_event_lineage_graph"]

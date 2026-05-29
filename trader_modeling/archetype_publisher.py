"""trader_modeling.archetype_publisher — Publish classified archetypes.

Receives ClassificationResults and:
  1. Publishes to the cognitive event bus (INDIRA_INSIGHT channel)
  2. Persists to the memory tensor (trader_patterns store) if available
  3. Emits a ledger event for audit/replay (INTELLIGENCE stream, INDIRA source)

Authority (B1): imports only core.*, state.*, trader_modeling.*.
INV-15: ts_ns is caller-supplied.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict, deque
from typing import Any

from trader_modeling.behavioral_classifier import ClassificationResult

_logger = logging.getLogger(__name__)

# Minimum confidence to publish as an INDIRA_INSIGHT
_MIN_PUBLISH_CONFIDENCE: float = 0.55

# Minimum number of new classifications before re-publishing same archetype
_MIN_REPUBLISH_INTERVAL: int = 20


class ArchetypePublisher:
    """Publishes behavioral classifications to the operator-visible surfaces.

    Deduplicates: only publishes when the dominant archetype changes for a
    symbol, or when confidence crosses a threshold.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # symbol → last published archetype
        self._last_published: dict[str, str] = {}
        # symbol → publish count
        self._publish_counts: dict[str, int] = defaultdict(int)
        # symbol → recent results for snapshot
        self._recent: dict[str, deque[ClassificationResult]] = {}
        self._total_published: int = 0

    def publish(self, result: ClassificationResult) -> bool:
        """Publish a classification result if it warrants operator attention.

        Returns True if the event was published.
        """
        if result.confidence < _MIN_PUBLISH_CONFIDENCE:
            return False

        with self._lock:
            last = self._last_published.get(result.symbol)
            count = self._publish_counts[result.symbol]
            changed = (last != result.archetype)
            interval_ok = (count % _MIN_REPUBLISH_INTERVAL == 0)

            if not changed and not interval_ok:
                self._publish_counts[result.symbol] += 1
                self._track(result)
                return False

            self._last_published[result.symbol] = result.archetype
            self._publish_counts[result.symbol] += 1
            self._total_published += 1
            self._track(result)

        self._emit_insight(result, changed=changed)
        self._persist_to_memory(result)
        self._emit_ledger(result)
        return True

    def snapshot(self, symbol: str | None = None, limit: int = 20) -> dict[str, Any]:
        """Return the current classification state for all or one symbol."""
        with self._lock:
            if symbol:
                recents = self._recent.get(symbol, deque())
                return {
                    "symbol": symbol,
                    "last_archetype": self._last_published.get(symbol),
                    "publish_count": self._publish_counts.get(symbol, 0),
                    "recent": [_result_to_dict(r) for r in list(recents)[-limit:]],
                }
            return {
                "total_published": self._total_published,
                "symbols": list(self._last_published.keys()),
                "last_archetypes": dict(self._last_published),
            }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _track(self, result: ClassificationResult) -> None:
        """Keep a rolling buffer of recent results per symbol (lock must be held)."""
        if result.symbol not in self._recent:
            self._recent[result.symbol] = deque(maxlen=50)
        self._recent[result.symbol].append(result)

    def _emit_insight(self, result: ClassificationResult, *, changed: bool) -> None:
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().publish(CognitiveChannel.INDIRA_INSIGHT, {
                "subject": "TRADER_ARCHETYPE_CLASSIFIED",
                "body": (
                    f"{'New' if changed else 'Confirmed'} dominant archetype "
                    f"on {result.symbol}: {result.archetype} "
                    f"(conf={result.confidence:.2f})"
                ),
                "archetype": result.archetype,
                "symbol": result.symbol,
                "confidence": result.confidence,
                "changed": changed,
                "scores": result.scores,
                "ts_ns": result.ts_ns,
            })
        except Exception as exc:
            _logger.debug("ArchetypePublisher: event bus error: %s", exc)

    def _persist_to_memory(self, result: ClassificationResult) -> None:
        try:
            from state.memory_tensor.trader_patterns.archetype_store import (
                get_archetype_store,
            )
            store = get_archetype_store()
            store.upsert(
                symbol=result.symbol,
                archetype=result.archetype,
                confidence=result.confidence,
                ts_ns=result.ts_ns,
                metadata={"scores": result.scores},
            )
        except Exception:
            pass

    def _emit_ledger(self, result: ClassificationResult) -> None:
        try:
            from state.ledger.append import append_event
            append_event(
                stream="INTELLIGENCE",
                kind="TRADER_ARCHETYPE",
                source="INDIRA",
                payload={
                    "symbol": result.symbol,
                    "archetype": result.archetype,
                    "confidence": result.confidence,
                    "scores": result.scores,
                    "signal_count": result.signal_count,
                    "mean_aggression": result.mean_aggression,
                    "mean_direction": result.mean_direction,
                    "mean_speed": result.mean_speed,
                    "ts_ns": result.ts_ns,
                },
            )
        except Exception:
            pass


def _result_to_dict(r: ClassificationResult) -> dict[str, Any]:
    return {
        "ts_ns": r.ts_ns,
        "symbol": r.symbol,
        "archetype": r.archetype,
        "confidence": r.confidence,
        "signal_count": r.signal_count,
    }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_publisher: ArchetypePublisher | None = None
_publisher_lock = threading.Lock()


def get_archetype_publisher() -> ArchetypePublisher:
    """Return the process-wide ArchetypePublisher singleton."""
    global _publisher
    with _publisher_lock:
        if _publisher is None:
            _publisher = ArchetypePublisher()
    return _publisher


__all__ = [
    "ArchetypePublisher",
    "get_archetype_publisher",
]

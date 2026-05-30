"""trader_modeling.trader_modeling_runtime — Orchestrates trader intelligence pipeline.

Drives the three-stage pipeline:
  ProfileExtractor → BehavioralClassifier → ArchetypePublisher

Also hooks into the event bus to receive live market ticks and feed them
into the extractor continuously.

On each tick():
  - For each symbol with enough signals, run classification
  - Publish newly classified archetypes to INDIRA_INSIGHT + ledger
  - Snapshot available via snapshot()

Authority (B1): imports only core.*, state.*, trader_modeling.*.
INV-15: ts_ns is caller-supplied; no wall-clock reads inside tick().
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from trader_modeling.archetype_publisher import get_archetype_publisher
from trader_modeling.behavioral_classifier import get_behavioral_classifier
from trader_modeling.profile_extractor import get_profile_extractor

_logger = logging.getLogger(__name__)


class TraderModelingRuntime:
    """Orchestrates the full trader behavioral intelligence pipeline.

    Args:
        tick_interval: run a classification pass every N ticks
    """

    def __init__(self, *, tick_interval: int = 30) -> None:
        self._lock = threading.Lock()
        self._tick_interval = max(1, tick_interval)
        self._tick_count = 0
        self._classification_count = 0
        self._market_ticks_ingested = 0
        self._subscribed = False

    # ------------------------------------------------------------------
    # Activation
    # ------------------------------------------------------------------

    def activate(self) -> None:
        """Subscribe to market tick events from the event bus.  Idempotent."""
        with self._lock:
            if self._subscribed:
                return
            self._subscribed = True
        self._subscribe_to_market_ticks()
        _logger.info("TraderModelingRuntime activated — subscribed to MARKET_TICK")

    # ------------------------------------------------------------------
    # Primary tick — classification pass
    # ------------------------------------------------------------------

    def tick(self, *, ts_ns: int) -> int:
        """Run a classification pass over all symbols with enough signals.

        Returns the number of classifications performed this tick.
        """
        with self._lock:
            self._tick_count += 1
            should_run = self._tick_count % self._tick_interval == 0

        if not should_run:
            return 0

        extractor = get_profile_extractor()
        classifier = get_behavioral_classifier()
        publisher = get_archetype_publisher()

        classified = 0
        for symbol in extractor.symbols():
            batch = extractor.get_batch(symbol, ts_ns)
            if batch is None:
                continue
            try:
                result = classifier.classify(batch, ts_ns)
                if publisher.publish(result):
                    classified += 1
            except Exception as exc:
                _logger.debug("TraderModelingRuntime: classify error [%s]: %s", symbol, exc)

        if classified:
            _logger.debug(
                "TraderModelingRuntime: %d new classifications (tick %d)",
                classified, self._tick_count,
            )

        with self._lock:
            self._classification_count += classified
        return classified

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            tc = self._tick_count
            cc = self._classification_count
            mt = self._market_ticks_ingested

        extractor_snap = get_profile_extractor().snapshot()
        publisher_snap = get_archetype_publisher().snapshot()

        return {
            "runtime": "TraderModelingRuntime",
            "tick_count": tc,
            "classification_count": cc,
            "market_ticks_ingested": mt,
            "extractor": extractor_snap,
            "publisher": publisher_snap,
        }

    # ------------------------------------------------------------------
    # Event bus subscription
    # ------------------------------------------------------------------

    def _subscribe_to_market_ticks(self) -> None:
        """Subscribe to MARKET_TICK channel to feed the extractor live data."""
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            bus = get_event_bus()

            def _on_tick(payload: dict[str, Any]) -> None:
                ts_ns = int(payload.get("ts_ns", 0))
                if ts_ns <= 0:
                    from system.time_source import wall_ns
                    ts_ns = wall_ns()
                try:
                    get_profile_extractor().ingest(payload, ts_ns)
                    with self._lock:
                        self._market_ticks_ingested += 1
                except Exception:
                    pass

            bus.subscribe(CognitiveChannel.MARKET_TICK, _on_tick)
        except Exception as exc:
            _logger.debug("TraderModelingRuntime: event bus subscribe error: %s", exc)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_runtime: TraderModelingRuntime | None = None
_runtime_lock = threading.Lock()


def get_trader_modeling_runtime(*, tick_interval: int = 30) -> TraderModelingRuntime:
    """Return the process-wide TraderModelingRuntime singleton."""
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            _runtime = TraderModelingRuntime(tick_interval=tick_interval)
    return _runtime


__all__ = [
    "TraderModelingRuntime",
    "get_trader_modeling_runtime",
]

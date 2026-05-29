"""intelligence_engine.cognitive.consciousness_stream — Indira Consciousness Stream.

The single operator-facing narrative aggregator.  Subscribes to all 8 cognitive
event bus channels and formats each event into a clear, human-readable narrative
entry.  Maintains a 200-entry rolling ring buffer of INDIRA's "inner monologue"
that the operator console and SSE stream consume.

This is the layer that makes INDIRA *visibly alive*:
  - Every thought becomes a sentence: "Analysing regime_assessment: regime belief
    maintained pending new signal evidence."
  - Every belief shift becomes: "Belief updated — BTC short-term trend: +0.14
    (driver: VWAP reclaim + order-flow imbalance)"
  - Every causal chain becomes: "Causal chain ACTIVE: CPI_SURPRISE → RISK_OFF →
    BTC_FLUSH (confidence 0.71)"
  - Every archetype shift becomes: "Dominant cluster changed: momentum_trader
    (7 members, 0.82 strength)"
  - System events become: "DYON detected B1 violation in execution_engine.hot_path"

A `ConsciousnessEntry` has an `importance` field (0.0–1.0) so the dashboard
can visually weight entries by significance — CONFIRMED causal chains and risk
breaches float to the top.

Authority (B1): intelligence_engine.*, state.*, core.* only.
INV-15: ts_ns is caller-supplied; no wall-clock reads.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass
from typing import Any

_logger = logging.getLogger(__name__)

_MAX_BUFFER: int = 200
_ENTRY_ID_COUNTER: int = 0
_ENTRY_LOCK = threading.Lock()


def _next_entry_id() -> str:
    global _ENTRY_ID_COUNTER
    with _ENTRY_LOCK:
        _ENTRY_ID_COUNTER += 1
        return f"cs_{_ENTRY_ID_COUNTER:06d}"


# ---------------------------------------------------------------------------
# Consciousness Entry
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConsciousnessEntry:
    """One narrative entry in INDIRA's consciousness stream."""

    entry_id: str
    ts_ns: int
    event_kind: str         # e.g. "THOUGHT", "BELIEF", "CAUSAL", "CLUSTER", "SYSTEM"
    narrative: str          # Human-readable sentence
    importance: float       # 0.0–1.0 — used for visual weighting in dashboard
    source: str             # "INDIRA" | "DYON" | "SYSTEM" | "RESEARCH"
    raw_sub_type: str = ""  # Original event sub-type for filtering

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "ts_ns": self.ts_ns,
            "event_kind": self.event_kind,
            "narrative": self.narrative,
            "importance": round(self.importance, 3),
            "source": self.source,
            "raw_sub_type": self.raw_sub_type,
        }


# ---------------------------------------------------------------------------
# ConsciousnessStream
# ---------------------------------------------------------------------------


class ConsciousnessStream:
    """INDIRA's live inner monologue — the operator's window into her mind.

    Subscribes to all 8 CognitiveChannel channels on activate() and converts
    each event into a natural-language narrative entry stored in a ring buffer.

    The ring buffer is safe to read from any thread via recent_entries().
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buffer: deque[ConsciousnessEntry] = deque(maxlen=_MAX_BUFFER)
        self._activated: bool = False
        self._entry_count: int = 0

    # ------------------------------------------------------------------
    # Activation
    # ------------------------------------------------------------------

    def activate(self) -> None:
        """Subscribe to all cognitive event channels.  Idempotent."""
        with self._lock:
            if self._activated:
                return
            self._activated = True

        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            bus = get_event_bus()
            bus.subscribe(CognitiveChannel.INDIRA_THOUGHT, self._on_thought)
            bus.subscribe(CognitiveChannel.INDIRA_INSIGHT, self._on_insight)
            bus.subscribe(CognitiveChannel.DYON_VIOLATION, self._on_dyon_violation)
            bus.subscribe(CognitiveChannel.DYON_PROPOSAL, self._on_dyon_proposal)
            bus.subscribe(CognitiveChannel.DYON_SCAN_COMPLETE, self._on_dyon_scan)
            bus.subscribe(CognitiveChannel.RESEARCH_COMPLETE, self._on_research)
            bus.subscribe(CognitiveChannel.MARKET_TICK, self._on_market_tick)
            bus.subscribe(CognitiveChannel.RISK_BREACH, self._on_risk_breach)
            _logger.info("ConsciousnessStream: activated — subscribed to all 8 channels")
        except Exception as exc:
            _logger.debug("ConsciousnessStream: subscribe error: %s", exc)

    # ------------------------------------------------------------------
    # Direct narrative injection (for hooks that don't go through the bus)
    # ------------------------------------------------------------------

    def record(
        self,
        ts_ns: int,
        event_kind: str,
        narrative: str,
        importance: float = 0.3,
        source: str = "INDIRA",
        raw_sub_type: str = "",
    ) -> ConsciousnessEntry:
        """Directly append a narrative entry to the stream."""
        entry = ConsciousnessEntry(
            entry_id=_next_entry_id(),
            ts_ns=ts_ns,
            event_kind=event_kind,
            narrative=narrative[:300],
            importance=max(0.0, min(1.0, importance)),
            source=source,
            raw_sub_type=raw_sub_type,
        )
        with self._lock:
            self._buffer.append(entry)
            self._entry_count += 1
        return entry

    # ------------------------------------------------------------------
    # Read surface
    # ------------------------------------------------------------------

    def recent_entries(self, limit: int = 50) -> list[ConsciousnessEntry]:
        """Return recent entries, newest-first."""
        with self._lock:
            items = list(self._buffer)
        items.reverse()
        return items[:limit]

    def recent_by_kind(self, event_kind: str, limit: int = 20) -> list[ConsciousnessEntry]:
        """Return recent entries filtered by event_kind."""
        all_entries = self.recent_entries(limit * 4)
        return [e for e in all_entries if e.event_kind == event_kind][:limit]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            activated = self._activated
            total = self._entry_count
            recent = list(self._buffer)[-10:]
        recent.reverse()
        return {
            "runtime": "ConsciousnessStream",
            "activated": activated,
            "total_entries": total,
            "buffer_size": min(total, _MAX_BUFFER),
            "recent_narratives": [e.to_dict() for e in recent],
        }

    def format_for_context(self) -> str:
        """Compact recent narrative fragment for ThoughtRuntime injection."""
        entries = self.recent_entries(3)
        if not entries:
            return ""
        top = entries[0]
        return f"last_stream_event={top.event_kind!r} narrative={top.narrative[:60]!r}"

    # ------------------------------------------------------------------
    # Event bus handlers (each formats payload → narrative, then records)
    # ------------------------------------------------------------------

    def _on_thought(self, payload: dict[str, Any]) -> None:
        step = str(payload.get("step", "reasoning"))
        ts_ns = int(payload.get("ts_ns", 0))
        conf = float(payload.get("confidence", 0.65))
        narrative = f"Thinking [{step.replace('_', ' ')}] — confidence {conf:.0%}"
        self.record(ts_ns, "THOUGHT", narrative, importance=0.20, source="INDIRA",
                    raw_sub_type="THOUGHT_STREAM")

    def _on_insight(self, payload: dict[str, Any]) -> None:
        subject = str(payload.get("subject", "insight"))
        body = str(payload.get("body", ""))
        ts_ns = int(payload.get("ts_ns", 0))
        conf = float(payload.get("confidence", 0.5))

        if subject == "TOP_TRADER_ARCHETYPE":
            narrative = f"Archetype shift detected — {body[:120]}"
            importance = 0.65
        elif subject == "REGIME_PATTERN":
            narrative = f"Long-horizon insight: {body[:120]}"
            importance = 0.70
        elif subject == "CONFIDENCE_TREND":
            narrative = f"Confidence trend update: {body[:120]}"
            importance = 0.50
        elif subject == "TRADER_ARCHETYPE_OBSERVED":
            archetype = str(payload.get("archetype", subject))
            narrative = f"Trader archetype observed: {archetype.replace('_', ' ')} (conf {conf:.0%})"
            importance = 0.30
        else:
            narrative = f"Insight [{subject}]: {body[:120]}"
            importance = 0.45

        self.record(ts_ns, "INSIGHT", narrative, importance=importance, source="INDIRA",
                    raw_sub_type="INDIRA_INSIGHT")

    def _on_dyon_violation(self, payload: dict[str, Any]) -> None:
        inv_id = str(payload.get("invariant_id", "?"))
        module = str(payload.get("source_module", "?"))
        severity = str(payload.get("severity", "?"))
        ts_ns = int(payload.get("ts_ns", 0))
        narrative = f"DYON violation [{severity}]: {inv_id} in {module}"
        importance = 0.80 if severity in ("CRITICAL", "ERROR") else 0.55
        self.record(ts_ns, "SYSTEM", narrative, importance=importance, source="DYON",
                    raw_sub_type="DYON_VIOLATION")

    def _on_dyon_proposal(self, payload: dict[str, Any]) -> None:
        desc = str(payload.get("description", "patch proposal"))
        ts_ns = int(payload.get("ts_ns", 0))
        mutation_class = str(payload.get("mutation_class", "?"))
        narrative = f"DYON proposes [{mutation_class}]: {desc[:120]}"
        self.record(ts_ns, "SYSTEM", narrative, importance=0.60, source="DYON",
                    raw_sub_type="DYON_PROPOSAL")

    def _on_dyon_scan(self, payload: dict[str, Any]) -> None:
        files = int(payload.get("files_scanned", 0))
        violations = int(payload.get("violation_count", 0))
        ts_ns = int(payload.get("ts_ns", 0))
        if violations == 0:
            narrative = f"DYON scan complete — {files} files, system clean"
            importance = 0.20
        else:
            narrative = f"DYON scan complete — {files} files, {violations} violation(s) detected"
            importance = 0.55 if violations < 5 else 0.75
        self.record(ts_ns, "SYSTEM", narrative, importance=importance, source="DYON",
                    raw_sub_type="DYON_SCAN_COMPLETE")

    def _on_research(self, payload: dict[str, Any]) -> None:
        topic = str(payload.get("topic", "unknown topic"))
        status = str(payload.get("status", "?"))
        trust = float(payload.get("trust_score", 0.5))
        ts_ns = int(payload.get("ts_ns", 0))
        narrative = f"Research {'complete' if status == 'ok' else 'failed'}: '{topic}' — trust {trust:.0%}"
        importance = 0.55 if status == "ok" and trust >= 0.6 else 0.30
        self.record(ts_ns, "RESEARCH", narrative, importance=importance, source="RESEARCH",
                    raw_sub_type="RESEARCH_COMPLETE")

    def _on_market_tick(self, payload: dict[str, Any]) -> None:
        symbol = str(payload.get("symbol", "?"))
        price = payload.get("price", None)
        ts_ns = int(payload.get("ts_ns", 0))
        if price is not None:
            narrative = f"Market tick: {symbol} @ {price}"
            self.record(ts_ns, "MARKET", narrative, importance=0.10, source="SYSTEM",
                        raw_sub_type="MARKET_TICK")

    def _on_risk_breach(self, payload: dict[str, Any]) -> None:
        reason = str(payload.get("reason", "unknown breach"))
        ts_ns = int(payload.get("ts_ns", 0))
        narrative = f"RISK BREACH: {reason}"
        self.record(ts_ns, "RISK", narrative, importance=1.0, source="SYSTEM",
                    raw_sub_type="RISK_BREACH")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_stream: ConsciousnessStream | None = None
_stream_lock = threading.Lock()


def get_consciousness_stream() -> ConsciousnessStream:
    """Return the process-wide ConsciousnessStream singleton."""
    global _stream
    with _stream_lock:
        if _stream is None:
            _stream = ConsciousnessStream()
    return _stream


__all__ = [
    "ConsciousnessEntry",
    "ConsciousnessStream",
    "get_consciousness_stream",
]

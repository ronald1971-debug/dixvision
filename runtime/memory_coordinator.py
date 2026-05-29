"""runtime.memory_coordinator — Automatic Cognitive Memory Capture.

Subscribes to the cognitive event bus and automatically writes important
cognitive events into the appropriate memory stores:

  INDIRA_THOUGHT    → EpisodicMemory  (what INDIRA reasoned about)
  INDIRA_INSIGHT    → SemanticMemory  (durable knowledge / patterns)
  RESEARCH_COMPLETE → SemanticMemory  (discovered external knowledge)
  DYON_PROPOSAL     → ProceduralMemory (proposed architectural action)

This closes the loop between live cognition and long-term memory formation:
cognitive events are no longer ephemeral — they are captured, persisted,
and queryable by future cognitive cycles.

Authority: runtime tier — imports state.*, intelligence_engine.* (read-only).
INV-15: ts_ns is read from event payloads (publisher-supplied).
B1: never imports execution_engine.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from typing import Any

_logger = logging.getLogger(__name__)

_EMBED_DIM = 64  # must match EpisodicMemoryStore / SemanticMemoryStore dim


def _hash_embed(text: str) -> tuple[float, ...]:
    """Deterministic hash-based embedding for text (no ML model needed).

    Maps text → a 64-dim float vector in [0, 1] via SHA-256 chunks.
    Consistent for the same text (INV-15 safe — no randomness).
    """
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).digest()
    # Repeat digest to fill 64 floats (256 bits = 32 bytes → repeat twice + trim)
    extended = (digest * 3)[:_EMBED_DIM]
    return tuple(b / 255.0 for b in extended)


class MemoryCoordinator:
    """Auto-captures cognitive events from the event bus into memory stores.

    Activated once at boot; then runs reactively via event bus subscriptions.
    All writes are best-effort — failures are logged at DEBUG level and ignored.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = False
        self._counts: dict[str, int] = {
            "episodes": 0,
            "semantic": 0,
            "procedural": 0,
            "errors": 0,
        }

    def activate(self) -> None:
        """Subscribe to cognitive channels.  Idempotent."""
        with self._lock:
            if self._active:
                return
            self._active = True

        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            bus = get_event_bus()
            bus.subscribe(CognitiveChannel.INDIRA_THOUGHT, self._on_thought)
            bus.subscribe(CognitiveChannel.INDIRA_INSIGHT, self._on_insight)
            bus.subscribe(CognitiveChannel.RESEARCH_COMPLETE, self._on_research)
            bus.subscribe(CognitiveChannel.DYON_PROPOSAL, self._on_proposal)
            # Activate Unified Cognitive Memory Layer (Stage 4)
            try:
                from state.memory.unified import get_unified_memory_layer
                get_unified_memory_layer().activate()
            except Exception as exc2:
                _logger.debug("MemoryCoordinator: unified layer activation failed: %s", exc2)
            _logger.info("MemoryCoordinator: activated (4 channels + unified layer)")
        except Exception as exc:
            _logger.debug("MemoryCoordinator.activate error: %s", exc)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"active": self._active, "counts": dict(self._counts)}

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_thought(self, payload: dict[str, Any]) -> None:
        """INDIRA_THOUGHT → EpisodicMemory + UnifiedMemoryLayer."""
        try:
            from state.memory_tensor.memory_orchestrator import get_memory_orchestrator
            from state.memory_tensor.contracts import Episode
            ts_ns = int(payload.get("ts_ns", 0))
            text = str(payload.get("reasoning_step", payload.get("thought", "")))
            ep = Episode(
                ts_ns=ts_ns,
                episode_id=f"thought_{ts_ns}",
                embedding=_hash_embed(text[:200]),
                payload={
                    "type": "INDIRA_THOUGHT",
                    "reasoning_step": text[:500],
                    "confidence": str(payload.get("confidence", "")),
                    "conclusion": str(payload.get("conclusion", "")),
                },
            )
            get_memory_orchestrator().write_episode(ep)
            # Unified layer dual-write
            try:
                from state.memory.contracts import MemoryKind
                from state.memory.unified import get_unified_memory_layer
                get_unified_memory_layer().write(
                    kind=MemoryKind.EPISODIC,
                    ts_ns=ts_ns or 1,
                    source="indira.thought_runtime",
                    summary=text[:200] or "INDIRA thought",
                    body={"reasoning_step": text[:500], "confidence": str(payload.get("confidence", ""))},
                    tags=frozenset(["indira", "thought"]),
                    confidence=float(payload.get("confidence", -1.0)) if payload.get("confidence") is not None else -1.0,
                )
            except Exception:
                pass
            with self._lock:
                self._counts["episodes"] += 1
        except Exception as exc:
            with self._lock:
                self._counts["errors"] += 1
            _logger.debug("MemoryCoordinator._on_thought error: %s", exc)

    def _on_insight(self, payload: dict[str, Any]) -> None:
        """INDIRA_INSIGHT → SemanticMemory + UnifiedMemoryLayer."""
        try:
            from state.memory_tensor.memory_orchestrator import get_memory_orchestrator
            from state.memory_tensor.contracts import Episode
            ts_ns = int(payload.get("ts_ns", 0))
            text = str(payload.get("body", payload.get("subject", "")))
            ep = Episode(
                ts_ns=ts_ns,
                episode_id=f"insight_{ts_ns}",
                embedding=_hash_embed(text[:200]),
                payload={
                    "type": "INDIRA_INSIGHT",
                    "subject": str(payload.get("subject", "")),
                    "body": text[:500],
                    "confidence": str(payload.get("confidence", "")),
                },
            )
            get_memory_orchestrator().write_semantic(ep)
            try:
                from state.memory.contracts import MemoryKind
                from state.memory.unified import get_unified_memory_layer
                subject = str(payload.get("subject", ""))
                get_unified_memory_layer().write(
                    kind=MemoryKind.SEMANTIC,
                    ts_ns=ts_ns or 1,
                    source="indira.long_horizon_memory",
                    summary=subject[:200] or text[:200] or "INDIRA insight",
                    body={"subject": subject[:200], "body": text[:500]},
                    tags=frozenset(["indira", "insight", "semantic"]),
                    confidence=float(payload.get("confidence", -1.0)) if payload.get("confidence") is not None else -1.0,
                )
            except Exception:
                pass
            with self._lock:
                self._counts["semantic"] += 1
        except Exception as exc:
            with self._lock:
                self._counts["errors"] += 1
            _logger.debug("MemoryCoordinator._on_insight error: %s", exc)

    def _on_research(self, payload: dict[str, Any]) -> None:
        """RESEARCH_COMPLETE → SemanticMemory + UnifiedMemoryLayer."""
        try:
            from state.memory_tensor.memory_orchestrator import get_memory_orchestrator
            from state.memory_tensor.contracts import Episode
            ts_ns = int(payload.get("ts_ns", 0))
            topic = str(payload.get("topic", ""))
            summary = str(payload.get("summary", payload.get("result_summary", "")))
            text = f"{topic}: {summary}"
            ep = Episode(
                ts_ns=ts_ns,
                episode_id=f"research_{ts_ns}",
                embedding=_hash_embed(text[:200]),
                payload={
                    "type": "RESEARCH_COMPLETE",
                    "topic": topic[:200],
                    "summary": summary[:500],
                    "confidence": str(payload.get("confidence", "")),
                    "source_url": str(payload.get("source_url", "")),
                },
            )
            get_memory_orchestrator().write_semantic(ep)
            try:
                from state.memory.contracts import MemoryKind
                from state.memory.unified import get_unified_memory_layer
                get_unified_memory_layer().write(
                    kind=MemoryKind.SEMANTIC,
                    ts_ns=ts_ns or 1,
                    source="intelligence_engine.research",
                    summary=f"[research] {topic[:100]}: {summary[:100]}",
                    body={"topic": topic[:200], "summary": summary[:500], "source_url": str(payload.get("source_url", ""))},
                    tags=frozenset(["research", "semantic", "external"]),
                    confidence=float(payload.get("confidence", -1.0)) if payload.get("confidence") is not None else -1.0,
                )
            except Exception:
                pass
            with self._lock:
                self._counts["semantic"] += 1
        except Exception as exc:
            with self._lock:
                self._counts["errors"] += 1
            _logger.debug("MemoryCoordinator._on_research error: %s", exc)

    def _on_proposal(self, payload: dict[str, Any]) -> None:
        """DYON_PROPOSAL → ProceduralMemory + UnifiedMemoryLayer."""
        try:
            from state.memory_tensor.memory_orchestrator import get_memory_orchestrator
            from state.memory_tensor.contracts import Episode
            ts_ns = int(payload.get("ts_ns", 0))
            action = str(payload.get("action", payload.get("instruction_type", "")))
            target = str(payload.get("target_file", payload.get("target", "")))
            text = f"{action} @ {target}"
            ep = Episode(
                ts_ns=ts_ns,
                episode_id=f"proposal_{payload.get('patch_id', ts_ns)}",
                embedding=_hash_embed(text[:200]),
                payload={
                    "type": "DYON_PROPOSAL",
                    "action": action[:200],
                    "target": target[:200],
                    "sim_outcome": str(payload.get("sim_outcome", "PENDING")),
                    "rationale": str(payload.get("rationale", ""))[:300],
                },
            )
            get_memory_orchestrator().write_procedural(ep)
            try:
                from state.memory.contracts import MemoryKind
                from state.memory.unified import get_unified_memory_layer
                get_unified_memory_layer().write(
                    kind=MemoryKind.PROCEDURAL,
                    ts_ns=ts_ns or 1,
                    source="dyon.evolution_engine",
                    summary=f"[dyon proposal] {action[:100]} @ {target[:100]}",
                    body={"action": action[:200], "target": target[:200], "rationale": str(payload.get("rationale", ""))[:300]},
                    tags=frozenset(["dyon", "proposal", "procedural"]),
                )
            except Exception:
                pass
            with self._lock:
                self._counts["procedural"] += 1
        except Exception as exc:
            with self._lock:
                self._counts["errors"] += 1
            _logger.debug("MemoryCoordinator._on_proposal error: %s", exc)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_coordinator: MemoryCoordinator | None = None
_coordinator_lock = threading.Lock()


def get_memory_coordinator() -> MemoryCoordinator:
    global _coordinator
    with _coordinator_lock:
        if _coordinator is None:
            _coordinator = MemoryCoordinator()
    return _coordinator


__all__ = [
    "MemoryCoordinator",
    "get_memory_coordinator",
]

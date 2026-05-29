"""intelligence_engine.cognitive.market_observation_session — ObservationSessionManager.

Represents INDIRA's focused attention: at any given moment she is *actively
observing* one or more market phenomena, forming hypotheses about what she is
seeing, and tracking whether those hypotheses are confirmed or dissolved.

An ObservationSession is spawned when a significant signal cluster is detected
— a regime shift, a new dominant behavioral cluster, a causal chain activating,
or a sustained confidence movement.  INDIRA can hold up to MAX_CONCURRENT sessions.

Hypothesis lifecycle within a session:
    FORMING     — first evidence received; thesis not yet testable
    ACTIVE      — 2+ observations support it; actively being tested
    CONFIRMED   — strong evidence consensus (confidence ≥ 0.70)
    REJECTED    — contradictory evidence dominates (confidence < 0.20)
    DISSOLVED   — session expired before resolution

Sessions are closed when:
    - All hypotheses resolved (confirmed or rejected)
    - Tick count exceeds SESSION_TTL_TICKS
    - Confidence collapsed below SESSION_MIN_CONFIDENCE

Authority (B1): intelligence_engine.*, state.*, core.* only.
INV-15: ts_ns is caller-supplied; no wall-clock reads.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from dataclasses import dataclass, field
from typing import Any

_logger = logging.getLogger(__name__)

MAX_CONCURRENT_SESSIONS: int = 3
SESSION_TTL_TICKS: int = 500
SESSION_MIN_CONFIDENCE: float = 0.15
HYPOTHESIS_CONFIRM_THRESHOLD: float = 0.70
HYPOTHESIS_REJECT_THRESHOLD: float = 0.20


# ---------------------------------------------------------------------------
# Hypothesis
# ---------------------------------------------------------------------------


@dataclass
class Hypothesis:
    """One hypothesis within an observation session."""

    hypo_id: str
    text: str                           # human-readable thesis
    status: str = "FORMING"            # FORMING | ACTIVE | CONFIRMED | REJECTED | DISSOLVED
    confidence: float = 0.45
    evidence_for: int = 0
    evidence_against: int = 0
    formed_ts_ns: int = 0

    def add_evidence(self, supporting: bool, weight: float = 1.0) -> None:
        if supporting:
            self.evidence_for += 1
            self.confidence = min(0.95, self.confidence + 0.06 * weight)
        else:
            self.evidence_against += 1
            self.confidence = max(0.0, self.confidence - 0.05 * weight)

        if self.status == "FORMING" and (self.evidence_for + self.evidence_against) >= 2:
            self.status = "ACTIVE"
        if self.confidence >= HYPOTHESIS_CONFIRM_THRESHOLD:
            self.status = "CONFIRMED"
        if self.confidence < HYPOTHESIS_REJECT_THRESHOLD and self.status not in ("CONFIRMED",):
            self.status = "REJECTED"

    def is_resolved(self) -> bool:
        return self.status in ("CONFIRMED", "REJECTED", "DISSOLVED")

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypo_id": self.hypo_id,
            "text": self.text,
            "status": self.status,
            "confidence": round(self.confidence, 3),
            "evidence_for": self.evidence_for,
            "evidence_against": self.evidence_against,
        }


# ---------------------------------------------------------------------------
# Observation Session
# ---------------------------------------------------------------------------


@dataclass
class ObservationSession:
    """INDIRA's focused observation on a specific market phenomenon."""

    session_id: str
    focus_label: str            # e.g. "BTC_REGIME_SHIFT", "ETH_FUNDING_EXTREME"
    theme: str                  # human-readable theme, e.g. "Evaluating momentum dominance"
    hypotheses: list[Hypothesis] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)  # raw signal strings
    started_ts_ns: int = 0
    last_active_ts_ns: int = 0
    tick_age: int = 0
    session_confidence: float = 0.50
    is_active: bool = True
    close_reason: str = ""

    def add_observation(self, signal: str, ts_ns: int) -> None:
        self.observations.append(signal[:120])
        if len(self.observations) > 20:
            self.observations = self.observations[-20:]
        self.last_active_ts_ns = ts_ns

    def primary_hypothesis(self) -> Hypothesis | None:
        return self.hypotheses[0] if self.hypotheses else None

    def all_resolved(self) -> bool:
        if not self.hypotheses:
            return False
        return all(h.is_resolved() for h in self.hypotheses)

    def update_confidence(self) -> None:
        if not self.hypotheses:
            return
        self.session_confidence = sum(h.confidence for h in self.hypotheses) / len(self.hypotheses)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "focus_label": self.focus_label,
            "theme": self.theme,
            "is_active": self.is_active,
            "session_confidence": round(self.session_confidence, 3),
            "tick_age": self.tick_age,
            "observations_count": len(self.observations),
            "recent_observations": self.observations[-3:],
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "close_reason": self.close_reason,
        }


# ---------------------------------------------------------------------------
# ObservationSessionManager
# ---------------------------------------------------------------------------


class ObservationSessionManager:
    """Manages INDIRA's concurrent observation sessions.

    Sessions are spawned from external triggers (regime change, cluster shift,
    causal chain activation) and from internal thought analysis.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, ObservationSession] = {}
        self._closed_sessions: list[ObservationSession] = []   # ring of last 20
        self._tick_count: int = 0
        self._spawn_count: int = 0
        self._activated: bool = False

    # ------------------------------------------------------------------
    # Activation
    # ------------------------------------------------------------------

    def activate(self) -> None:
        """Subscribe to event bus for regime/cluster signals.  Idempotent."""
        with self._lock:
            if self._activated:
                return
            self._activated = True
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            bus = get_event_bus()
            bus.subscribe(CognitiveChannel.INDIRA_INSIGHT, self._on_insight)
            bus.subscribe(CognitiveChannel.DYON_SCAN_COMPLETE, self._on_dyon_scan)
            _logger.info("ObservationSessionManager: activated")
        except Exception as exc:
            _logger.debug("ObservationSessionManager: subscribe error: %s", exc)

    # ------------------------------------------------------------------
    # Tick — called each INDIRA reasoning cycle
    # ------------------------------------------------------------------

    def tick(self, ts_ns: int, thought_context: str = "") -> None:
        """Advance all sessions one tick.

        - Ages sessions; closes stale or resolved ones.
        - Feeds thought_context into active session hypotheses.
        - Optionally spawns new sessions from context signals.
        """
        with self._lock:
            self._tick_count += 1
            to_close: list[str] = []

            for sid, session in self._sessions.items():
                session.tick_age += 1
                session.update_confidence()

                # Expire
                if session.tick_age >= SESSION_TTL_TICKS:
                    session.is_active = False
                    session.close_reason = "ttl_expired"
                    to_close.append(sid)
                    continue
                if session.session_confidence < SESSION_MIN_CONFIDENCE:
                    session.is_active = False
                    session.close_reason = "confidence_collapsed"
                    to_close.append(sid)
                    continue
                if session.all_resolved():
                    session.is_active = False
                    session.close_reason = "all_hypotheses_resolved"
                    to_close.append(sid)
                    continue

                # Feed thought context into active sessions
                if thought_context:
                    session.add_observation(thought_context[:80], ts_ns)
                    self._update_hypotheses_from_context(session, thought_context)

            # Close expired sessions
            for sid in to_close:
                s = self._sessions.pop(sid)
                self._closed_sessions.append(s)
                if len(self._closed_sessions) > 20:
                    self._closed_sessions = self._closed_sessions[-20:]

        # Spawn new sessions from context signals (outside main lock)
        if thought_context:
            self._try_spawn_from_context(thought_context, ts_ns)

    # ------------------------------------------------------------------
    # Spawn API — external callers trigger new sessions
    # ------------------------------------------------------------------

    def spawn_session(
        self,
        focus_label: str,
        theme: str,
        initial_hypothesis_text: str,
        ts_ns: int,
    ) -> str | None:
        """Spawn a new observation session.

        Returns session_id or None if at capacity or duplicate focus exists.
        """
        with self._lock:
            # Don't spawn duplicate focus labels
            for s in self._sessions.values():
                if s.focus_label == focus_label and s.is_active:
                    return None
            if len(self._sessions) >= MAX_CONCURRENT_SESSIONS:
                # Close the oldest to make room
                oldest = min(self._sessions.values(), key=lambda s: s.started_ts_ns)
                oldest.is_active = False
                oldest.close_reason = "evicted_for_new_focus"
                self._closed_sessions.append(self._sessions.pop(oldest.session_id))

            self._spawn_count += 1
            raw = f"{focus_label}:{ts_ns}:{self._spawn_count}".encode()
            short = hashlib.blake2b(raw, digest_size=4).hexdigest()
            sid = f"obs_{short}"
            hypo_id = f"h_{short}_0"

            session = ObservationSession(
                session_id=sid,
                focus_label=focus_label,
                theme=theme,
                hypotheses=[Hypothesis(
                    hypo_id=hypo_id,
                    text=initial_hypothesis_text,
                    formed_ts_ns=ts_ns,
                    confidence=0.45,
                )],
                started_ts_ns=ts_ns,
                last_active_ts_ns=ts_ns,
            )
            self._sessions[sid] = session
            _logger.info(
                "ObservationSessionManager: spawned session %s focus=%s", sid, focus_label
            )
            return sid

    # ------------------------------------------------------------------
    # Read surface
    # ------------------------------------------------------------------

    def active_sessions(self) -> list[ObservationSession]:
        with self._lock:
            return [s for s in self._sessions.values() if s.is_active]

    def format_for_context(self) -> str:
        """Compact observation context for ThoughtRuntime injection."""
        sessions = self.active_sessions()
        if not sessions:
            return ""
        # Show the highest-confidence active session
        top = max(sessions, key=lambda s: s.session_confidence)
        ph = top.primary_hypothesis()
        if ph:
            return f"observing={top.focus_label!r} hypo={ph.text[:60]!r} conf={top.session_confidence:.2f}"
        return f"observing={top.focus_label!r} conf={top.session_confidence:.2f}"

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            active = [s.to_dict() for s in self._sessions.values() if s.is_active]
            recent_closed = [s.to_dict() for s in self._closed_sessions[-5:]]
            return {
                "runtime": "ObservationSessionManager",
                "tick_count": self._tick_count,
                "spawn_count": self._spawn_count,
                "active_session_count": len(active),
                "active_sessions": active,
                "recent_closed": recent_closed,
            }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_insight(self, payload: dict[str, Any]) -> None:
        """Handle INDIRA_INSIGHT — spawn sessions for archetype/regime shifts."""
        subject = str(payload.get("subject", ""))
        ts_ns = int(payload.get("ts_ns", 0))
        body = str(payload.get("body", ""))
        if not ts_ns:
            return

        if subject == "TOP_TRADER_ARCHETYPE":
            # New dominant archetype — observe it
            self.spawn_session(
                focus_label=f"ARCHETYPE_SHIFT",
                theme="Evaluating new dominant trader archetype",
                initial_hypothesis_text=f"New archetype dominance reflects current regime: {body[:80]}",
                ts_ns=ts_ns,
            )
        elif subject == "REGIME_PATTERN":
            self.spawn_session(
                focus_label="REGIME_PATTERN",
                theme="Investigating dominant market regime pattern",
                initial_hypothesis_text=f"Regime pattern suggests: {body[:80]}",
                ts_ns=ts_ns,
            )

    def _on_dyon_scan(self, payload: dict[str, Any]) -> None:
        """Handle DYON scan — spawn session if violations detected."""
        ts_ns = int(payload.get("ts_ns", 0))
        violation_count = int(payload.get("violation_count", 0))
        if violation_count >= 3 and ts_ns:
            self.spawn_session(
                focus_label="SYSTEM_STRESS",
                theme="DYON detected elevated structural violations — cognitive load rising",
                initial_hypothesis_text=f"System stress ({violation_count} violations) may degrade cognitive quality",
                ts_ns=ts_ns,
            )

    def _try_spawn_from_context(self, context: str, ts_ns: int) -> None:
        """Spawn sessions from thought context tokens (causal triggers)."""
        ctx_l = context.lower()
        triggers = [
            ("funding_extreme" in ctx_l or "funding_positive_extreme" in ctx_l,
             "FUNDING_EXTREME", "Evaluating funding rate extreme", "Elevated funding indicates overleveraged longs"),
            ("regime_shift" in ctx_l or "regime change" in ctx_l,
             "REGIME_SHIFT", "Tracking potential regime transition", "Regime transition may invalidate current strategy allocations"),
            ("vix_spike" in ctx_l or "macro_fear" in ctx_l,
             "MACRO_FEAR", "Evaluating macro fear contagion into crypto", "VIX/macro fear typically causes correlated crypto sell-off"),
        ]
        for condition, focus, theme, hypo_text in triggers:
            if condition:
                self.spawn_session(focus, theme, hypo_text, ts_ns)

    @staticmethod
    def _update_hypotheses_from_context(
        session: ObservationSession,
        context: str,
    ) -> None:
        """Update hypothesis confidence from thought context signals."""
        ctx_l = context.lower()
        for hypo in session.hypotheses:
            if hypo.is_resolved():
                continue
            # Very simple heuristic: if key terms from the hypothesis appear in context,
            # treat as supporting evidence
            hypo_terms = set(hypo.text.lower().split())
            ctx_terms = set(ctx_l.split())
            overlap = len(hypo_terms & ctx_terms)
            if overlap >= 2:
                hypo.add_evidence(supporting=True, weight=0.4)
            elif "contradiction" in ctx_l or "reversed" in ctx_l or "failed" in ctx_l:
                hypo.add_evidence(supporting=False, weight=0.5)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_manager: ObservationSessionManager | None = None
_manager_lock = threading.Lock()


def get_observation_session_manager() -> ObservationSessionManager:
    """Return the process-wide ObservationSessionManager singleton."""
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = ObservationSessionManager()
    return _manager


__all__ = [
    "Hypothesis",
    "ObservationSession",
    "ObservationSessionManager",
    "get_observation_session_manager",
]

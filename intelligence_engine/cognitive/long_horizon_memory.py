"""LongHorizonMemory — INDIRA's persistent self-model across time (P0 Emergence).

INDIRA's 20-thought reflection window captures only the last few minutes of
cognition.  LongHorizonMemory operates at a much slower timescale — reading
the full thought ledger, DyonMemory's persistent violations, and completed
research results — to extract patterns that persist across days of operation.

Four insight types are extracted per consolidation run:

    REGIME_PATTERN      — which market regime dominates the thought stream
    CONFIDENCE_TREND    — is INDIRA's cognitive confidence improving or declining
    SYSTEM_STRESS       — DYON's structural violation count as cognitive load
    RESEARCH_SYNTHESIS  — what INDIRA knows from completed research tasks

Insights are:
    * Persisted to SQLite via CognitionPersistenceStore (survive restarts).
    * Expired by TTL so stale beliefs do not accumulate forever.
    * Formatted as a compact context prefix injected into every IndiraRuntime
      tick via EnvironmentAwareness or a dedicated hook.

Authority (B1): imports only from intelligence_engine.* and core.*.
All cross-boundary reads (evolution_engine, state.*) are lazy + best-effort.
INV-15: ts_ns is caller-supplied; no wall-clock reads inside any method.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

_logger = logging.getLogger(__name__)

_STORE_KIND = "long_horizon_insights"
_INSIGHT_TTL_NS = 24 * 3_600 * 1_000_000_000   # 24 h
_MIN_THOUGHTS_FOR_REGIME = 10
_MIN_THOUGHTS_FOR_TREND = 5
_LEDGER_FETCH_LIMIT = 500   # thought rows to read from ledger per consolidation


# ---------------------------------------------------------------------------
# Insight record
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Insight:
    """One persistent belief produced by LongHorizonMemory."""

    insight_id: str
    ts_ns: int
    subject: str        # "REGIME_PATTERN" | "CONFIDENCE_TREND" | "SYSTEM_STRESS" | "RESEARCH_SYNTHESIS"
    body: str           # human-readable summary
    confidence: float
    evidence_count: int
    expires_ns: int     # nanosecond timestamp after which this insight is stale

    def is_live(self, *, ts_ns: int) -> bool:
        return ts_ns < self.expires_ns

    def to_dict(self) -> dict[str, Any]:
        return {
            "insight_id": self.insight_id,
            "ts_ns": self.ts_ns,
            "subject": self.subject,
            "body": self.body,
            "confidence": self.confidence,
            "evidence_count": self.evidence_count,
            "expires_ns": self.expires_ns,
        }


# ---------------------------------------------------------------------------
# LongHorizonMemory
# ---------------------------------------------------------------------------


class LongHorizonMemory:
    """INDIRA's self-model across time.

    Consolidate every ``consolidate_interval`` ticks (managed by the caller);
    each run reads historical signals, derives insights, persists them, and
    makes them available for context injection.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._insights: dict[str, Insight] = {}   # subject → latest insight
        self._consolidate_count = 0
        self._restore()

    # ------------------------------------------------------------------
    # Primary API
    # ------------------------------------------------------------------

    def consolidate(self, *, ts_ns: int) -> list[Insight]:
        """Run one consolidation pass.  Returns the list of new/updated insights."""
        self._consolidate_count += 1
        new_insights: list[Insight] = []

        regime = self._extract_regime_pattern(ts_ns)
        if regime is not None:
            new_insights.append(regime)

        trend = self._extract_confidence_trend(ts_ns)
        if trend is not None:
            new_insights.append(trend)

        stress = self._extract_system_stress(ts_ns)
        if stress is not None:
            new_insights.append(stress)

        research = self._extract_research_synthesis(ts_ns)
        if research is not None:
            new_insights.append(research)

        with self._lock:
            for ins in new_insights:
                self._insights[ins.subject] = ins

        self._persist(ts_ns)
        self._publish_insights(new_insights)

        if new_insights:
            _logger.info(
                "LongHorizonMemory: %d insights consolidated (pass #%d)",
                len(new_insights),
                self._consolidate_count,
            )
        return new_insights

    def _publish_insights(self, insights: list[Insight]) -> None:
        """Publish each new insight as an INDIRA_INSIGHT event on the bus."""
        if not insights:
            return
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            bus = get_event_bus()
            for ins in insights:
                bus.publish(CognitiveChannel.INDIRA_INSIGHT, {
                    "insight_id": ins.insight_id,
                    "subject": ins.subject,
                    "body": ins.body,
                    "confidence": ins.confidence,
                    "evidence_count": ins.evidence_count,
                    "ts_ns": ins.ts_ns,
                })
        except Exception:
            pass

    def active_insights(self, *, ts_ns: int) -> list[Insight]:
        """Return all non-expired insights, newest first."""
        with self._lock:
            live = [ins for ins in self._insights.values() if ins.is_live(ts_ns=ts_ns)]
        return sorted(live, key=lambda i: -i.ts_ns)

    def format_for_context(self, *, ts_ns: int, limit: int = 3) -> str:
        """Return a compact key=value prefix for ThoughtRuntime context injection.

        At most *limit* insights are included, highest-confidence first.
        Returns an empty string if no live insights exist.
        """
        insights = sorted(
            self.active_insights(ts_ns=ts_ns),
            key=lambda i: -i.confidence,
        )[:limit]
        if not insights:
            return ""
        parts = []
        for ins in insights:
            key = ins.subject.lower()
            # Truncate body to first sentence for compactness
            body = ins.body.split(".")[0].strip()
            parts.append(f"{key}={body!r}")
        return " ".join(parts)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._insights)
        return {
            "consolidate_count": self._consolidate_count,
            "total_insights": total,
            "store_kind": _STORE_KIND,
        }

    # ------------------------------------------------------------------
    # Extraction routines
    # ------------------------------------------------------------------

    def _extract_regime_pattern(self, ts_ns: int) -> Insight | None:
        """Read the thought ledger; find the dominant market regime."""
        try:
            import json as _json
            from state.ledger.event_store import get_event_store
            rows = get_event_store().query(
                event_type="INTELLIGENCE",
                source="INDIRA",
                limit=_LEDGER_FETCH_LIMIT,
            )
            regime_counter: Counter[str] = Counter()
            conf_by_regime: dict[str, list[float]] = {}
            for row in rows:
                if row.get("sub_type") != "THOUGHT_STREAM":
                    continue
                raw = row.get("payload", "{}")
                p = _json.loads(raw) if isinstance(raw, str) else raw
                if not isinstance(p, dict):
                    continue
                step = str(p.get("reasoning_step", ""))
                if step not in ("regime_assessment", "self_reflection"):
                    continue
                context = str(p.get("context", ""))
                for token in context.split():
                    if "=" in token:
                        k, _, v = token.partition("=")
                        if k == "regime":
                            regime_counter[v] += 1
                            conf_by_regime.setdefault(v, []).append(
                                float(p.get("confidence", 0.65))
                            )
            if sum(regime_counter.values()) < _MIN_THOUGHTS_FOR_REGIME:
                return None

            dominant, count = regime_counter.most_common(1)[0]
            total = sum(regime_counter.values())
            prevalence = count / total
            mean_conf = (
                sum(conf_by_regime.get(dominant, [0.65]))
                / max(len(conf_by_regime.get(dominant, [1])), 1)
            )
            body = (
                f"{dominant} has been the dominant regime in {count}/{total} "
                f"assessed thought cycles ({prevalence:.0%} prevalence)."
            )
            return self._make_insight(
                subject="REGIME_PATTERN",
                body=body,
                confidence=min(0.90, mean_conf * prevalence + 0.30),
                evidence_count=count,
                ts_ns=ts_ns,
            )
        except Exception as exc:
            _logger.debug("LongHorizonMemory._extract_regime_pattern error: %s", exc)
            return None

    def _extract_confidence_trend(self, ts_ns: int) -> Insight | None:
        """Compute a long-horizon confidence slope from ledger thought rows."""
        try:
            import json as _json
            from state.ledger.event_store import get_event_store
            rows = get_event_store().query(
                event_type="INTELLIGENCE",
                source="INDIRA",
                limit=_LEDGER_FETCH_LIMIT,
            )
            series: list[tuple[int, float]] = []
            for row in rows:
                if row.get("sub_type") != "THOUGHT_STREAM":
                    continue
                raw = row.get("payload", "{}")
                p = _json.loads(raw) if isinstance(raw, str) else raw
                if not isinstance(p, dict):
                    continue
                try:
                    thought_ts = int(row.get("ts_ns", 0))
                    conf = float(p.get("confidence", 0.0))
                    if thought_ts > 0 and 0.0 <= conf <= 1.0:
                        series.append((thought_ts, conf))
                except (ValueError, TypeError):
                    continue

            if len(series) < _MIN_THOUGHTS_FOR_TREND:
                return None

            series.sort(key=lambda x: x[0])
            xs = [float(i) for i in range(len(series))]
            ys = [c for _, c in series]
            slope = _linear_slope(xs, ys)
            mean_conf = sum(ys) / len(ys)

            if slope > 0.0005:
                direction = "improving"
                adj_conf = min(0.85, mean_conf + 0.10)
            elif slope < -0.0005:
                direction = "declining"
                adj_conf = max(0.35, mean_conf - 0.05)
            else:
                direction = "stable"
                adj_conf = mean_conf

            body = (
                f"Cognitive confidence is {direction} "
                f"(slope={slope:+.4f}, mean={mean_conf:.2f} over {len(series)} observations)."
            )
            return self._make_insight(
                subject="CONFIDENCE_TREND",
                body=body,
                confidence=adj_conf,
                evidence_count=len(series),
                ts_ns=ts_ns,
            )
        except Exception as exc:
            _logger.debug("LongHorizonMemory._extract_confidence_trend error: %s", exc)
            return None

    def _extract_system_stress(self, ts_ns: int) -> Insight | None:
        # evolution_engine.dyon is an offline engine — L3 prohibits reading
        # its memory from the runtime.  System stress is reported as clean
        # until a state-contract bridge is wired in a future wave.
        return None

    def _extract_research_synthesis(self, ts_ns: int) -> Insight | None:
        """Synthesise the most recent completed research topics into a belief."""
        try:
            from state.cognition_persistence import get_cognition_persistence_store
            results = get_cognition_persistence_store().load_recent_results(limit=20)
            if not results:
                return None

            completed = [r for r in results if r.get("status") == "ok"]
            if not completed:
                return None

            high_trust = [r for r in completed if float(r.get("trust_score", 0)) >= 0.6]
            topics = [r.get("topic", "") for r in completed[:5]]
            topic_str = "; ".join(t for t in topics if t)

            mean_trust = (
                sum(float(r.get("trust_score", 0.5)) for r in completed) / len(completed)
            )
            body = (
                f"{len(completed)} research tasks completed "
                f"({len(high_trust)} high-trust). "
                f"Recent topics: {topic_str}."
            )
            return self._make_insight(
                subject="RESEARCH_SYNTHESIS",
                body=body,
                confidence=min(0.85, mean_trust),
                evidence_count=len(completed),
                ts_ns=ts_ns,
            )
        except Exception as exc:
            _logger.debug("LongHorizonMemory._extract_research_synthesis error: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self, ts_ns: int) -> None:
        try:
            from state.cognition_persistence import get_cognition_persistence_store
            ps = get_cognition_persistence_store()
            with self._lock:
                blobs = {s: ins.to_dict() for s, ins in self._insights.items()}
            ps.save_episode(
                store_kind=_STORE_KIND,
                episode_id=f"lhm_snapshot_{self._consolidate_count}",
                ts_ns=ts_ns,
                data={"insights": blobs},
            )
        except Exception as exc:
            _logger.debug("LongHorizonMemory._persist error: %s", exc)

    def _restore(self) -> None:
        try:
            from state.cognition_persistence import get_cognition_persistence_store
            rows = get_cognition_persistence_store().load_episodes(_STORE_KIND, limit=1)
            if not rows:
                return
            blobs = rows[0].get("insights", {})
            for subject, d in blobs.items():
                try:
                    self._insights[subject] = Insight(
                        insight_id=str(d["insight_id"]),
                        ts_ns=int(d["ts_ns"]),
                        subject=str(d["subject"]),
                        body=str(d["body"]),
                        confidence=float(d["confidence"]),
                        evidence_count=int(d["evidence_count"]),
                        expires_ns=int(d["expires_ns"]),
                    )
                except Exception:
                    pass
            if self._insights:
                _logger.info(
                    "LongHorizonMemory: restored %d insights from persistence",
                    len(self._insights),
                )
        except Exception as exc:
            _logger.debug("LongHorizonMemory._restore error: %s", exc)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_insight(
        *,
        subject: str,
        body: str,
        confidence: float,
        evidence_count: int,
        ts_ns: int,
    ) -> Insight:
        raw = f"{subject}:{body}"
        short = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return Insight(
            insight_id=f"lhm_{short}_{ts_ns & 0xFFFFFF:06x}",
            ts_ns=ts_ns,
            subject=subject,
            body=body,
            confidence=max(0.0, min(1.0, confidence)),
            evidence_count=evidence_count,
            expires_ns=ts_ns + _INSIGHT_TTL_NS,
        )


# ---------------------------------------------------------------------------
# Linear slope helper (no numpy, INV-15 safe)
# ---------------------------------------------------------------------------


def _linear_slope(xs: list[float], ys: list[float]) -> float:
    """Ordinary-least-squares slope for paired (xs, ys)."""
    n = len(xs)
    if n < 2:
        return 0.0
    x_bar = sum(xs) / n
    y_bar = sum(ys) / n
    num = sum((xi - x_bar) * (yi - y_bar) for xi, yi in zip(xs, ys))
    den = sum((xi - x_bar) ** 2 for xi in xs)
    return num / den if den != 0.0 else 0.0


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_memory: LongHorizonMemory | None = None
_memory_lock = threading.Lock()


def get_long_horizon_memory() -> LongHorizonMemory:
    """Return the process-wide LongHorizonMemory singleton."""
    global _memory
    with _memory_lock:
        if _memory is None:
            _memory = LongHorizonMemory()
    return _memory


__all__ = [
    "Insight",
    "LongHorizonMemory",
    "get_long_horizon_memory",
]

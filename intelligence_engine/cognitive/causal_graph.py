"""intelligence_engine.cognitive.causal_graph — INDIRA Causal Reasoning Graph.

INDIRA doesn't just observe market events — she reasons about WHY they happen
and WHAT they will trigger next.  CausalReasoningGraph maintains a live set of
causal hypotheses drawn from pre-seeded macro chains and updated by incoming
evidence from thought contexts, market state, and event bus signals.

Chain lifecycle:
    FORMING     — chain activated by first root-cause observation
    ACTIVE      — evidence accumulating; 2+ links observed or time-weighted
    CONFIRMED   — all expected effects materialized; confidence ≥ 0.70
    WEAKENED    — contradictory evidence; confidence declining below 0.35
    DISSOLVED   — stale (> TTL) or confidence < 0.10

Design:
* Pre-seeded with 9 standard macro causal chains covering crypto/rates/risk.
* `observe_context(context_str, ts_ns)` — parses INDIRA thought context for
  event label tokens and updates matching hypotheses.
* `observe_event(event_label, ts_ns)` — direct signal injection (used by the
  market state bridge or environment awareness).
* `tick(ts_ns)` — decays stale hypotheses, promotes/demotes status, emits
  CausalChainEvents for active/confirmed hypotheses.
* `format_for_context()` — compact key=value prefix for ThoughtRuntime injection.

Authority (B1): intelligence_engine.*, state.*, core.* only.
INV-15: ts_ns is caller-supplied; no wall-clock reads inside any method.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from dataclasses import dataclass, field
from typing import Any

_logger = logging.getLogger(__name__)

# Hypothesis TTL: 4 hours in nanoseconds
_HYPO_TTL_NS: int = 4 * 3_600 * 1_000_000_000
# Minimum confidence to emit a CausalChainEvent
_EMIT_THRESHOLD: float = 0.40
# Confirmation threshold
_CONFIRM_THRESHOLD: float = 0.70
# Dissolution threshold
_DISSOLVE_THRESHOLD: float = 0.10
# Confidence decay per tick when no evidence arrives
_DECAY_PER_TICK: float = 0.002


# ---------------------------------------------------------------------------
# Pre-seeded causal chain knowledge
# Each entry: (chain_name, causes_labels, effects_labels)
# Labels are normalised upper-snake tokens INDIRA's context parser recognises.
# ---------------------------------------------------------------------------

_SEED_CHAINS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "cpi_shock_risk_off",
        ("CPI_SURPRISE", "INFLATION_BEAT",),
        ("RISK_OFF", "USD_STRENGTH", "BTC_FLUSH", "ALT_RECOVERY"),
    ),
    (
        "fed_hawkish_crypto_bear",
        ("FED_HAWKISH", "RATE_HIKE", "USD_STRENGTH"),
        ("RISK_OFF", "CRYPTO_BEAR", "BTC_SELL_OFF"),
    ),
    (
        "funding_flip_long_squeeze",
        ("FUNDING_POSITIVE_EXTREME", "OVERLEVERAGED_LONGS"),
        ("LONG_SQUEEZE", "PRICE_DROP", "OI_CONTRACTION"),
    ),
    (
        "oi_expansion_trend_continuation",
        ("OI_EXPANDING", "SPOT_BUYING", "VWAP_RECLAIM"),
        ("TREND_CONTINUATION", "MOMENTUM_CLUSTER_DOMINANT"),
    ),
    (
        "vix_spike_correlation",
        ("VIX_SPIKE", "MACRO_FEAR", "CORRELATION_ONE"),
        ("CRYPTO_SELL_OFF", "RISK_OFF", "LIQUIDITY_DRAIN"),
    ),
    (
        "whale_accumulation_recovery",
        ("SPOT_CVD_DIVERGENCE", "WHALE_BIDS", "OI_STABLE"),
        ("PRICE_RECOVERY", "SPOT_DEMAND_DOMINANT"),
    ),
    (
        "regime_bull_momentum",
        ("BULL_REGIME", "TREND_FOLLOWING", "POSITIVE_FUNDING"),
        ("MOMENTUM_CLUSTER_DOMINANT", "TREND_CONTINUATION", "HFT_ACTIVITY"),
    ),
    (
        "regime_bear_value_rotation",
        ("BEAR_REGIME", "RISK_OFF", "NEGATIVE_FUNDING"),
        ("MEAN_REVERSION_DOMINANT", "VALUE_CLUSTER_DOMINANT", "BTC_STABILISE"),
    ),
    (
        "mixed_regime_quant_edge",
        ("MIXED_REGIME", "LOW_VOLATILITY", "RANGE_BOUND"),
        ("QUANT_CLUSTER_DOMINANT", "SYSTEMATIC_DOMINANT", "MEAN_REVERSION_ACTIVE"),
    ),
)

# Token normalisation map: market context terms → canonical labels
_TOKEN_MAP: dict[str, str] = {
    # Regime tokens
    "bull": "BULL_REGIME",
    "bear": "BEAR_REGIME",
    "mixed": "MIXED_REGIME",
    "trending": "BULL_REGIME",
    # Risk tokens
    "risk-off": "RISK_OFF",
    "risk_off": "RISK_OFF",
    "riskoff": "RISK_OFF",
    # Inflation/macro
    "cpi": "CPI_SURPRISE",
    "inflation": "INFLATION_BEAT",
    "fed": "FED_HAWKISH",
    "rate_hike": "RATE_HIKE",
    "usd": "USD_STRENGTH",
    # Market structure
    "funding": "POSITIVE_FUNDING",
    "oi": "OI_EXPANDING",
    "vwap": "VWAP_RECLAIM",
    "vix": "VIX_SPIKE",
    "vol": "VOLATILITY",
    # Cluster labels from trader intelligence
    "momentum_cluster": "MOMENTUM_CLUSTER_DOMINANT",
    "value_cluster": "VALUE_CLUSTER_DOMINANT",
    "quant_cluster": "QUANT_CLUSTER_DOMINANT",
    "mean_reversion": "MEAN_REVERSION_DOMINANT",
}


# ---------------------------------------------------------------------------
# Hypothesis record (mutable per update cycle)
# ---------------------------------------------------------------------------


@dataclass
class CausalHypothesis:
    """One active causal chain hypothesis."""

    hypo_id: str
    chain_name: str
    causes: tuple[str, ...]
    effects: tuple[str, ...]
    observed_causes: set[str] = field(default_factory=set)
    observed_effects: set[str] = field(default_factory=set)
    confidence: float = 0.40
    ts_activated_ns: int = 0
    ts_last_evidence_ns: int = 0
    status: str = "FORMING"       # FORMING | ACTIVE | CONFIRMED | WEAKENED | DISSOLVED
    ticks_without_evidence: int = 0
    evidence_count: int = 0

    def cause_coverage(self) -> float:
        n = len(self.causes)
        return len(self.observed_causes) / n if n else 0.0

    def effect_coverage(self) -> float:
        n = len(self.effects)
        return len(self.observed_effects) / n if n else 0.0

    def all_causes_confirmed(self) -> bool:
        return self.observed_causes >= set(self.causes)

    def primary_effect_confirmed(self) -> bool:
        return bool(self.effects) and self.effects[0] in self.observed_effects

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypo_id": self.hypo_id,
            "chain_name": self.chain_name,
            "causes": list(self.causes),
            "effects": list(self.effects),
            "observed_causes": list(self.observed_causes),
            "observed_effects": list(self.observed_effects),
            "confidence": round(self.confidence, 3),
            "status": self.status,
            "cause_coverage": round(self.cause_coverage(), 2),
            "effect_coverage": round(self.effect_coverage(), 2),
            "evidence_count": self.evidence_count,
            "ts_activated_ns": self.ts_activated_ns,
        }


# ---------------------------------------------------------------------------
# CausalReasoningGraph
# ---------------------------------------------------------------------------


class CausalReasoningGraph:
    """INDIRA's live causal reasoning engine.

    Maintains a set of active hypotheses derived from pre-seeded chains.
    Hypotheses are activated when INDIRA observes root-cause events, then
    updated as downstream effects materialise.

    Args:
        max_active_hypotheses: Maximum concurrent active hypotheses before
            lowest-confidence ones are dissolved to make room.
    """

    def __init__(self, *, max_active_hypotheses: int = 6) -> None:
        self._lock = threading.Lock()
        self._hypotheses: dict[str, CausalHypothesis] = {}
        self._tick_count: int = 0
        self._max_active = max(2, max_active_hypotheses)
        self._last_emit_ns: dict[str, int] = {}   # hypo_id → last emit ts_ns
        # Emit throttle: same hypothesis won't emit more than once per 60s
        self._emit_throttle_ns: int = 60 * 1_000_000_000

    # ------------------------------------------------------------------
    # Primary API
    # ------------------------------------------------------------------

    def observe_context(self, context_str: str, ts_ns: int) -> int:
        """Parse INDIRA's thought context string for known causal labels.

        Tokenises on whitespace and punctuation, normalises, then calls
        observe_event for each recognised label.  Returns count of labels found.
        """
        if not context_str:
            return 0
        found = 0
        # Split on whitespace + common separators, lower-case
        raw_tokens = context_str.replace("=", " ").replace(",", " ").replace(
            ";", " "
        ).replace("→", " ").replace("->", " ").split()
        for tok in raw_tokens:
            tok_l = tok.lower().strip(".'\"()")
            label = _TOKEN_MAP.get(tok_l)
            if label is None:
                # Try raw upper-snake match directly (context may already have labels)
                upper = tok.upper().strip(".'\"()")
                for _, causes, effects in _SEED_CHAINS:
                    if upper in causes or upper in effects:
                        label = upper
                        break
            if label:
                self.observe_event(label, ts_ns)
                found += 1
        return found

    def observe_event(self, event_label: str, ts_ns: int) -> None:
        """Register one causal event label and update matching hypotheses.

        - If the label is a root cause of a known chain and no hypothesis is
          active for that chain, activate a new hypothesis.
        - If it matches a cause in an active hypothesis, increase confidence.
        - If it matches an expected effect, further increase confidence.
        """
        label = event_label.upper()
        with self._lock:
            # Update active hypotheses first
            for hypo in list(self._hypotheses.values()):
                if hypo.status == "DISSOLVED":
                    continue
                updated = False
                if label in hypo.causes and label not in hypo.observed_causes:
                    hypo.observed_causes.add(label)
                    hypo.confidence = min(0.95, hypo.confidence + 0.08 * hypo.cause_coverage())
                    hypo.evidence_count += 1
                    updated = True
                if label in hypo.effects and label not in hypo.observed_effects:
                    hypo.observed_effects.add(label)
                    hypo.confidence = min(0.95, hypo.confidence + 0.10)
                    hypo.evidence_count += 1
                    updated = True
                if updated:
                    hypo.ts_last_evidence_ns = ts_ns
                    hypo.ticks_without_evidence = 0
                    if hypo.status == "FORMING" and hypo.evidence_count >= 2:
                        hypo.status = "ACTIVE"

            # Activate new hypotheses for chains where label is a root cause
            for chain_name, causes, effects in _SEED_CHAINS:
                if label in causes:
                    existing = self._hypotheses.get(chain_name)
                    if existing is None or existing.status == "DISSOLVED":
                        self._activate_hypothesis(chain_name, causes, effects, label, ts_ns)

    def tick(self, ts_ns: int) -> list[str]:
        """Advance the causal reasoning cycle.

        - Decays confidence on hypotheses that haven't seen evidence recently.
        - Promotes ACTIVE→CONFIRMED when criteria met.
        - Marks WEAKENED/DISSOLVED when confidence falls.
        - Emits CausalChainEvents for active/confirmed hypotheses.
        - Culls lowest-confidence hypotheses if over max.

        Returns list of chain_names that were emitted this tick.
        """
        emitted: list[str] = []
        with self._lock:
            self._tick_count += 1
            for hypo in list(self._hypotheses.values()):
                if hypo.status == "DISSOLVED":
                    continue

                # Staleness check
                age_ns = ts_ns - hypo.ts_activated_ns
                if age_ns > _HYPO_TTL_NS and hypo.status not in ("CONFIRMED",):
                    hypo.status = "DISSOLVED"
                    continue

                # Decay
                hypo.ticks_without_evidence += 1
                if hypo.ticks_without_evidence > 5:
                    hypo.confidence = max(0.0, hypo.confidence - _DECAY_PER_TICK)

                # Promotion / demotion
                if (
                    hypo.status == "ACTIVE"
                    and hypo.confidence >= _CONFIRM_THRESHOLD
                    and (hypo.all_causes_confirmed() or hypo.primary_effect_confirmed())
                ):
                    hypo.status = "CONFIRMED"

                if hypo.confidence < 0.25 and hypo.status == "ACTIVE":
                    hypo.status = "WEAKENED"

                if hypo.confidence < _DISSOLVE_THRESHOLD:
                    hypo.status = "DISSOLVED"
                    continue

                # Emit if threshold met and not throttled
                if hypo.confidence >= _EMIT_THRESHOLD and hypo.status in ("ACTIVE", "CONFIRMED"):
                    last = self._last_emit_ns.get(hypo.hypo_id, 0)
                    if ts_ns - last >= self._emit_throttle_ns:
                        emitted.append(hypo.chain_name)
                        self._last_emit_ns[hypo.hypo_id] = ts_ns
                        # Emit outside lock below

            # Cull excess hypotheses (keep highest-confidence active ones)
            active = [
                h for h in self._hypotheses.values()
                if h.status not in ("DISSOLVED",)
            ]
            if len(active) > self._max_active:
                active.sort(key=lambda h: h.confidence)
                for h in active[:len(active) - self._max_active]:
                    h.status = "DISSOLVED"

        # Emit CausalChainEvents outside the lock
        for chain_name in emitted:
            self._emit_chain(chain_name, ts_ns)

        return emitted

    # ------------------------------------------------------------------
    # Read surface
    # ------------------------------------------------------------------

    def active_hypotheses(self) -> list[CausalHypothesis]:
        """Return non-dissolved hypotheses sorted by confidence desc."""
        with self._lock:
            live = [
                h for h in self._hypotheses.values()
                if h.status not in ("DISSOLVED",)
            ]
        return sorted(live, key=lambda h: -h.confidence)

    def format_for_context(self) -> str:
        """Compact causal context string for ThoughtRuntime injection."""
        hypos = self.active_hypotheses()
        if not hypos:
            return ""
        top = hypos[0]
        short_chain = "→".join(list(top.causes[:2]) + list(top.effects[:1]))
        return f"active_chain={short_chain!r} chain_conf={top.confidence:.2f}"

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            tick_count = self._tick_count
            hypos = [h.to_dict() for h in self._hypotheses.values()]
        active = [h for h in hypos if h["status"] not in ("DISSOLVED",)]
        return {
            "runtime": "CausalReasoningGraph",
            "tick_count": tick_count,
            "active_hypothesis_count": len(active),
            "total_hypothesis_count": len(hypos),
            "hypotheses": active,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _activate_hypothesis(
        self,
        chain_name: str,
        causes: tuple[str, ...],
        effects: tuple[str, ...],
        trigger_label: str,
        ts_ns: int,
    ) -> None:
        """Create a new hypothesis (called under lock)."""
        raw = f"{chain_name}:{ts_ns}".encode()
        short = hashlib.blake2b(raw, digest_size=4).hexdigest()
        hypo_id = f"causal_{chain_name[:16]}_{short}"
        hypo = CausalHypothesis(
            hypo_id=hypo_id,
            chain_name=chain_name,
            causes=causes,
            effects=effects,
            observed_causes={trigger_label},
            confidence=0.40,
            ts_activated_ns=ts_ns,
            ts_last_evidence_ns=ts_ns,
            status="FORMING",
            evidence_count=1,
        )
        self._hypotheses[chain_name] = hypo
        _logger.debug("CausalReasoningGraph: activated hypothesis %s", chain_name)

    def _emit_chain(self, chain_name: str, ts_ns: int) -> None:
        """Emit CausalChainEvent to ledger for the named hypothesis."""
        with self._lock:
            hypo = self._hypotheses.get(chain_name)
            if hypo is None:
                return
            snap = hypo.to_dict()

        try:
            from intelligence_engine.cognitive.observability_emitter import emit_causal_chain
            emit_causal_chain(
                ts_ns=ts_ns,
                hypothesis=f"{chain_name}: {snap['observed_causes']} → {snap['observed_effects']}",
                causes=tuple(snap["causes"]),
                effects=tuple(snap["effects"]),
                confidence=snap["confidence"],
                evidence_count=snap["evidence_count"],
                chain_id=snap["hypo_id"],
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_graph: CausalReasoningGraph | None = None
_graph_lock = threading.Lock()


def get_causal_graph() -> CausalReasoningGraph:
    """Return the process-wide CausalReasoningGraph singleton."""
    global _graph
    with _graph_lock:
        if _graph is None:
            _graph = CausalReasoningGraph()
    return _graph


__all__ = [
    "CausalHypothesis",
    "CausalReasoningGraph",
    "get_causal_graph",
]

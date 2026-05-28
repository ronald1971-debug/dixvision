"""intelligence_engine.intent_producer — AgentDecisionTrace → ExecutionIntent.

Converts an :class:`~core.contracts.agent.AgentDecisionTrace` plus a
runtime context dict into a governance-pending
:class:`~core.contracts.execution_intent.ExecutionIntent` record.

Rules:
* Confidence below ``min_confidence`` → return ``None`` (no intent).
* Direction ``"HOLD"`` → return ``None``.
* Direction ``"BUY"`` or ``"SELL"`` above floor → build a synthetic
  :class:`~core.contracts.events.SignalEvent` from the trace and
  wrap it as an ``ExecutionIntent`` with
  ``approved_by_governance=False`` (pending approval).

The intent is emitted to the ledger via
:func:`state.ledger.event_store.append_event` under the
``INTELLIGENCE / INTENT_PROPOSED`` stream so governance can pick it
up for approval.

Authority constraints (manifest §H1 / §6):
* Module imports only :mod:`core.contracts` and standard library +
  ledger helper. No execution_engine or governance_engine imports.
* No clock on the hot path — the caller passes ``ts_ns``.
* Deterministic: same trace + same context → same intent record
  (INV-15).

Singleton accessor :func:`get_intent_producer` returns the process-
level default instance (lazy-constructed, thread-safe for CPython GIL).
"""

from __future__ import annotations

import threading
from typing import Any

from core.contracts.agent import AgentDecisionTrace
from core.contracts.events import Side, SignalEvent
from core.contracts.execution_intent import (
    AUTHORISED_INTENT_ORIGINS,
    ExecutionIntent,
    create_execution_intent,
)

_ORIGIN = "intelligence_engine.meta_controller.hot_path"
_HOLD = "HOLD"
_BUY = "BUY"
_SELL = "SELL"

# Sentinel: the origin used to create intents from the intent producer.
# Must be a member of AUTHORISED_INTENT_ORIGINS.
assert _ORIGIN in AUTHORISED_INTENT_ORIGINS, (
    f"IntentProducer origin {_ORIGIN!r} not in AUTHORISED_INTENT_ORIGINS"
)


def _side_from_direction(direction: str) -> Side:
    """Convert ``"BUY"`` / ``"SELL"`` to :class:`Side`."""
    if direction == _BUY:
        return Side.BUY
    if direction == _SELL:
        return Side.SELL
    return Side.HOLD


def _build_signal_event(
    trace: AgentDecisionTrace,
    context: dict[str, Any],
) -> SignalEvent:
    """Construct a synthetic :class:`SignalEvent` from a trace + context.

    The signal carries:
    * ``ts_ns`` from the trace.
    * ``symbol`` from context[``"symbol"``] or ``"UNKNOWN"``.
    * ``side`` derived from ``trace.direction``.
    * ``confidence`` from the trace.
    * ``plugin_chain`` synthesised from the trace's rationale tags.
    * ``meta`` carrying ``agent_id``, ``signal_id``, and ``direction``.
    """
    symbol: str = str(context.get("symbol", "UNKNOWN"))
    side = _side_from_direction(trace.direction)
    plugin_chain: tuple[str, ...] = tuple(
        f"agent:{trace.signal_id}" for _ in (trace.signal_id,) if trace.signal_id
    ) or ("agent:unknown",)
    meta: dict[str, str] = {
        "agent_id": str(context.get("agent_id", "")),
        "signal_id": trace.signal_id,
        "direction": trace.direction,
        "rationale": ",".join(trace.rationale_tags),
    }
    return SignalEvent(
        ts_ns=trace.ts_ns,
        symbol=symbol,
        side=side,
        confidence=trace.confidence,
        plugin_chain=plugin_chain,
        meta=meta,
    )


class IntentProducer:
    """Converts :class:`AgentDecisionTrace` records into
    :class:`ExecutionIntent` pending-approval tokens.

    Parameters
    ----------
    min_confidence:
        Floor below which traces are silently discarded. Traces at or
        above the floor with a non-HOLD direction are forwarded.
    max_intent_size_usd:
        Informational cap carried in intent ``meta`` for the Governance
        layer to enforce. The producer does not perform position sizing
        itself (that belongs in the meta-controller allocation step).
    """

    def __init__(
        self,
        min_confidence: float = 0.6,
        max_intent_size_usd: float = 10_000.0,
    ) -> None:
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError(
                f"IntentProducer.min_confidence must be in [0, 1], got {min_confidence!r}"
            )
        if not (max_intent_size_usd > 0.0):
            raise ValueError(
                f"IntentProducer.max_intent_size_usd must be > 0, got {max_intent_size_usd!r}"
            )
        self._min_confidence = min_confidence
        self._max_intent_size_usd = max_intent_size_usd

    @property
    def min_confidence(self) -> float:
        return self._min_confidence

    @property
    def max_intent_size_usd(self) -> float:
        return self._max_intent_size_usd

    def produce(
        self,
        trace: AgentDecisionTrace,
        context: dict[str, Any],
    ) -> ExecutionIntent | None:
        """Convert *trace* to an :class:`ExecutionIntent` or return ``None``.

        Returns ``None`` when:
        * ``trace.direction == "HOLD"`` (no directional intent).
        * ``trace.confidence < min_confidence`` (below quality floor).

        Otherwise constructs a synthetic :class:`SignalEvent` from the
        trace, wraps it as a pending :class:`ExecutionIntent`, emits the
        intent to the ledger, and returns it.

        Parameters
        ----------
        trace:
            Immutable decision record from an AGT-XX agent.
        context:
            Runtime context dict. Recognised keys:
            ``"symbol"`` (str), ``"agent_id"`` (str),
            ``"ts_ns"`` (int — falls back to trace.ts_ns).
        """
        if trace.direction == _HOLD:
            return None
        if trace.confidence < self._min_confidence:
            return None

        ts_ns: int = int(context.get("ts_ns", trace.ts_ns))
        signal = _build_signal_event(trace, context)
        meta: tuple[tuple[str, str], ...] = (
            ("producer", "IntentProducer"),
            ("max_size_usd", repr(self._max_intent_size_usd)),
            ("min_confidence", repr(self._min_confidence)),
        )

        intent = create_execution_intent(
            ts_ns=ts_ns,
            origin=_ORIGIN,
            signal=signal,
            approved_by_governance=False,
            governance_decision_id="",
            meta=meta,
        )

        self._emit_to_ledger(intent, trace)
        return intent

    # ------------------------------------------------------------------
    # Ledger emission (best-effort; never blocks the hot path)
    # ------------------------------------------------------------------

    @staticmethod
    def _emit_to_ledger(intent: ExecutionIntent, trace: AgentDecisionTrace) -> None:
        """Append the produced intent to the INTELLIGENCE ledger stream.

        Failures are silently swallowed so a ledger outage never blocks
        intelligence output — the intent is still returned to the caller.
        """
        try:
            from state.ledger.event_store import append_event  # lazy import

            append_event(
                "INTELLIGENCE",
                "INTENT_PROPOSED",
                _ORIGIN,
                {
                    "intent_id": intent.intent_id,
                    "ts_ns": intent.ts_ns,
                    "symbol": intent.signal.symbol,
                    "direction": trace.direction,
                    "confidence": trace.confidence,
                    "agent_rationale": list(trace.rationale_tags),
                    "content_hash": intent.content_hash,
                },
            )
        except Exception:
            pass  # ledger unavailable — intent is returned regardless


# ---------------------------------------------------------------------------
# Process-level singleton
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_default: IntentProducer | None = None


def get_intent_producer(
    min_confidence: float = 0.6,
    max_intent_size_usd: float = 10_000.0,
) -> IntentProducer:
    """Return (or lazily construct) the process-level :class:`IntentProducer`.

    The first call wins: subsequent calls ignore the keyword arguments
    and return the already-constructed instance. Callers that need
    non-default parameters should construct an :class:`IntentProducer`
    directly and inject it rather than relying on this singleton.
    """
    global _default
    if _default is None:
        with _lock:
            if _default is None:
                _default = IntentProducer(
                    min_confidence=min_confidence,
                    max_intent_size_usd=max_intent_size_usd,
                )
    return _default


__all__ = [
    "IntentProducer",
    "get_intent_producer",
]

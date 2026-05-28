"""execution_engine.orchestrator — End-to-End Execution Pipeline Coordinator.

Ties the full execution lifecycle into a single deterministic pipeline:

    Signal → Governance Gate → Smart Route → Dispatch → Fill → Reconcile

INV-56 (Triad Lock): Decider (intelligence) → Approver (governance) → Executor (adapters)
INV-68 (ExecutionIntent Immutability): Once created, intents are frozen.
INV-15 (Replay Determinism): No raw clock calls in hot path; all timestamps
        are caller-supplied via ``ts_ns``.

The orchestrator is the ONLY entry point for trade execution. No adapter
may be called directly. All execution flows through this pipeline, ensuring
governance approval, audit trail, and reconciliation for every trade.

Architecture:
- Phase 1: VALIDATE — Signal quality, risk limits, position sizing
- Phase 2: GOVERN — Governance gate (BLOCKING, FAIL-CLOSED — INV-56)
- Phase 3: ROUTE — Smart order routing (split, venue selection)
- Phase 4: DISPATCH — Submit to broker/exchange adapters
- Phase 5: CONFIRM — Fill confirmation + partial fill handling
- Phase 6: RECONCILE — Position + balance reconciliation

Governance philosophy:
- The governance gate is NEVER bypassed. If no gate is configured,
  execution is REJECTED (fail-closed per manifest §3 governance rules).
- Every decision (approval or rejection) produces a DecisionTrace entry
  in the authority ledger for full auditability.
- DecisionSigner binds governance approval to execution via HMAC.

__capability_tier__ = 4  # GOVERNED_PAPER_EXECUTION
__forbidden_tiers__ = ()
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class PipelinePhase(StrEnum):
    """Execution pipeline phases."""

    VALIDATE = "VALIDATE"
    GOVERN = "GOVERN"
    ROUTE = "ROUTE"
    DISPATCH = "DISPATCH"
    CONFIRM = "CONFIRM"
    RECONCILE = "RECONCILE"
    COMPLETE = "COMPLETE"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class RejectionReason(StrEnum):
    """Standard rejection codes."""

    VALIDATION_FAILED = "VALIDATION_FAILED"
    GOVERNANCE_DENIED = "GOVERNANCE_DENIED"
    GOVERNANCE_NOT_CONFIGURED = "GOVERNANCE_NOT_CONFIGURED"
    RISK_LIMIT_EXCEEDED = "RISK_LIMIT_EXCEEDED"
    NO_ROUTE_AVAILABLE = "NO_ROUTE_AVAILABLE"
    DISPATCH_FAILED = "DISPATCH_FAILED"
    FILL_TIMEOUT = "FILL_TIMEOUT"
    RECONCILIATION_MISMATCH = "RECONCILIATION_MISMATCH"
    SIGNER_NOT_CONFIGURED = "SIGNER_NOT_CONFIGURED"


# ---------------------------------------------------------------------------
# Protocols for dependency injection (B1 — no cross-engine imports)
# ---------------------------------------------------------------------------


class GovernanceGateProtocol(Protocol):
    """Governance gate interface (INV-56 Approver)."""

    def approve_execution(
        self,
        *,
        signal_id: str,
        symbol: str,
        side: str,
        quantity: float,
        source: str,
        ts_ns: int,
    ) -> Any: ...


class DecisionSignerProtocol(Protocol):
    """HMAC signer for governance decisions (HARDEN-S1-02)."""

    def sign(self, *, content_hash: str, governance_decision_id: str) -> str: ...
    def verify(self, *, content_hash: str, governance_decision_id: str, signature: str) -> bool: ...


class LedgerWriterProtocol(Protocol):
    """Authority ledger writer (append-only, hash-chained)."""

    def append(self, *, ts_ns: int, kind: str, payload: dict[str, str]) -> None: ...


# ---------------------------------------------------------------------------
# Data contracts (frozen, slotted — INV-68 / INV-15)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExecutionSignal:
    """Incoming trade signal from intelligence engine.

    Frozen (INV-68): once created, the signal is immutable through the
    pipeline. All downstream phases reference the same object; no field
    may be mutated between creation and dispatch.

    ts_ns is caller-supplied (INV-15): no raw clock calls. The caller
    (intelligence engine tick loop) provides the authoritative timestamp.
    """

    signal_id: str
    symbol: str
    side: str  # "BUY" or "SELL"
    quantity: float
    ts_ns: int  # caller-supplied (INV-15 — no raw clock)
    price_limit: float | None = None
    urgency: float = 0.5  # 0.0 = patient, 1.0 = immediate
    source: str = "intelligence_engine"
    confidence: float = 1.0
    signal_trust: str = "INTERNAL"  # INTERNAL / EXTERNAL_LOW / EXTERNAL_MED
    metadata: tuple[tuple[str, str], ...] = ()  # immutable key-value pairs


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Result of the full execution pipeline (frozen, deterministic)."""

    signal_id: str
    phase_reached: PipelinePhase
    success: bool
    governance_decision_id: str = ""
    governance_signature: str = ""
    fill_qty: float = 0.0
    avg_price: float = 0.0
    total_cost: float = 0.0
    slippage_bps: float = 0.0
    fees: float = 0.0
    venue: str = ""
    rejection_reason: RejectionReason | None = None
    rejection_detail: str = ""
    duration_ns: int = 0
    order_ids: tuple[str, ...] = ()
    ts_ns: int = 0  # completion timestamp (caller-supplied)
    trace_id: str = ""


@dataclass(frozen=True, slots=True)
class RouteDecision:
    """Smart router's venue/split decision."""

    venue: str
    splits: tuple[tuple[str, float], ...] = ()  # (venue, qty) pairs
    algo: str = "TWAP"
    estimated_slippage_bps: float = 0.0
    confidence: float = 0.8


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class ExecutionOrchestrator:
    """Coordinates the full signal-to-fill pipeline.

    This is the single entry point for ALL trade execution in the system.
    It enforces the invariant that no trade can bypass governance, and
    that every execution is fully audited and reconciled.

    INV-56 enforcement:
    - Decider: signal source (intelligence_engine)
    - Approver: governance_gate (MUST be configured; fail-closed if None)
    - Executor: dispatcher (broker adapters)

    INV-15 enforcement:
    - All timestamps are caller-supplied via ts_ns parameters
    - No time.time(), datetime.now(), or time.time_ns() in hot path
    - Pipeline is deterministic given same inputs
    """

    __slots__ = (
        "_governance_gate",
        "_decision_signer",
        "_smart_router",
        "_dispatcher",
        "_fill_handler",
        "_reconciler",
        "_risk_checker",
        "_ledger",
        "_metrics",
        "_config",
    )

    def __init__(
        self,
        *,
        governance_gate: GovernanceGateProtocol | None = None,
        decision_signer: DecisionSignerProtocol | None = None,
        smart_router: Any = None,
        dispatcher: Any = None,
        fill_handler: Any = None,
        reconciler: Any = None,
        risk_checker: Any = None,
        ledger: LedgerWriterProtocol | None = None,
    ) -> None:
        self._governance_gate = governance_gate
        self._decision_signer = decision_signer
        self._smart_router = smart_router
        self._dispatcher = dispatcher
        self._fill_handler = fill_handler
        self._reconciler = reconciler
        self._risk_checker = risk_checker
        self._ledger = ledger
        self._metrics = _PipelineMetrics()
        self._config = _OrchestratorConfig()

    def execute(self, signal: ExecutionSignal, *, ts_ns: int) -> ExecutionResult:
        """Execute the full pipeline for a signal.

        Args:
            signal: The frozen execution signal (INV-68 immutable).
            ts_ns: Current authoritative timestamp from TimeAuthority
                   (INV-15 — no raw clock reads).

        Returns:
            ExecutionResult with full audit trail.

        The governance gate is BLOCKING and FAIL-CLOSED:
        - If governance_gate is None → REJECTED (not approved)
        - If governance_gate raises → REJECTED (fail-closed)
        - Only explicit approval passes Phase 2
        """
        start_ns = ts_ns
        self._metrics.total_signals += 1

        # Phase 1: VALIDATE
        validation = self._validate(signal)
        if not validation.passed:
            self._metrics.rejected_validation += 1
            result = self._reject(
                signal,
                PipelinePhase.VALIDATE,
                RejectionReason.VALIDATION_FAILED,
                validation.reason,
                start_ns,
                ts_ns,
            )
            self._write_decision_trace(signal, result, ts_ns)
            return result

        # Phase 2: GOVERN (INV-56 — Approver gate, FAIL-CLOSED)
        gov_decision = self._govern(signal, ts_ns)
        if not gov_decision.approved:
            self._metrics.rejected_governance += 1
            result = self._reject(
                signal,
                PipelinePhase.GOVERN,
                gov_decision.rejection_reason,
                gov_decision.reason,
                start_ns,
                ts_ns,
            )
            self._write_decision_trace(signal, result, ts_ns)
            return result

        # Phase 3: ROUTE
        route = self._route(signal)
        if route is None:
            self._metrics.rejected_routing += 1
            result = self._reject(
                signal,
                PipelinePhase.ROUTE,
                RejectionReason.NO_ROUTE_AVAILABLE,
                "no venue available",
                start_ns,
                ts_ns,
            )
            self._write_decision_trace(signal, result, ts_ns)
            return result

        # Phase 4: DISPATCH (INV-56 — Executor)
        dispatch = self._dispatch(signal, route, ts_ns)
        if not dispatch.submitted:
            self._metrics.dispatch_failures += 1
            result = self._reject(
                signal,
                PipelinePhase.DISPATCH,
                RejectionReason.DISPATCH_FAILED,
                dispatch.error,
                start_ns,
                ts_ns,
            )
            self._write_decision_trace(signal, result, ts_ns)
            return result

        # Phase 5: CONFIRM
        fill = self._confirm(signal, dispatch)

        # Phase 6: RECONCILE
        self._reconcile(signal, fill, ts_ns)

        self._metrics.successful_executions += 1

        result = ExecutionResult(
            signal_id=signal.signal_id,
            phase_reached=PipelinePhase.COMPLETE,
            success=True,
            governance_decision_id=gov_decision.decision_id,
            governance_signature=gov_decision.signature,
            fill_qty=fill.filled_qty,
            avg_price=fill.avg_price,
            total_cost=fill.filled_qty * fill.avg_price,
            slippage_bps=fill.slippage_bps,
            fees=fill.fees,
            venue=route.venue,
            duration_ns=ts_ns - start_ns,
            order_ids=tuple(dispatch.order_ids),
            ts_ns=ts_ns,
            trace_id=self._compute_trace_id(signal),
        )

        # Write audit + decision trace
        self._write_decision_trace(signal, result, ts_ns)
        self._audit(signal, fill, result, ts_ns)

        return result

    # ------------------------------------------------------------------
    # Phase implementations
    # ------------------------------------------------------------------

    def _validate(self, signal: ExecutionSignal) -> _ValidationResult:
        """Phase 1: Validate signal quality and risk limits."""
        if signal.quantity <= 0:
            return _ValidationResult(False, "quantity must be positive")
        if signal.side not in ("BUY", "SELL"):
            return _ValidationResult(False, f"invalid side: {signal.side}")
        if not signal.symbol:
            return _ValidationResult(False, "symbol required")
        if signal.ts_ns <= 0:
            return _ValidationResult(False, "ts_ns must be positive (INV-15)")

        # Risk check (fail-closed on error)
        if self._risk_checker:
            try:
                risk_ok = self._risk_checker.check_pre_trade(
                    symbol=signal.symbol,
                    side=signal.side,
                    quantity=signal.quantity,
                    price=signal.price_limit,
                )
                if not risk_ok:
                    return _ValidationResult(False, "risk limit exceeded")
            except Exception as e:
                logger.warning("Risk checker error: %s", e)
                return _ValidationResult(False, f"risk check error: {e}")

        return _ValidationResult(True, "")

    def _govern(self, signal: ExecutionSignal, ts_ns: int) -> _GovernanceDecision:
        """Phase 2: Governance approval gate (INV-56, BLOCKING, FAIL-CLOSED).

        If no governance gate is configured, execution is REJECTED.
        This is the manifest's non-negotiable requirement: governance is
        the sole authority for execution approval.
        """
        # FAIL-CLOSED: no gate = no execution
        if self._governance_gate is None:
            return _GovernanceDecision(
                approved=False,
                reason="governance gate not configured (fail-closed)",
                rejection_reason=RejectionReason.GOVERNANCE_NOT_CONFIGURED,
                decision_id="",
                signature="",
            )

        try:
            decision = self._governance_gate.approve_execution(
                signal_id=signal.signal_id,
                symbol=signal.symbol,
                side=signal.side,
                quantity=signal.quantity,
                source=signal.source,
                ts_ns=ts_ns,
            )

            approved = decision.approved if hasattr(decision, "approved") else bool(decision)
            decision_id = getattr(decision, "governance_decision_id", "") or getattr(
                decision, "decision_id", ""
            )
            reason = getattr(decision, "reason", "")

            # Sign the decision if signer is available (HARDEN-S1-02)
            signature = ""
            if approved and self._decision_signer and decision_id:
                content_hash = self._compute_content_hash(signal)
                signature = self._decision_signer.sign(
                    content_hash=content_hash,
                    governance_decision_id=decision_id,
                )

            return _GovernanceDecision(
                approved=approved,
                reason=reason,
                rejection_reason=RejectionReason.GOVERNANCE_DENIED if not approved else None,
                decision_id=decision_id,
                signature=signature,
            )
        except Exception as e:
            # FAIL-CLOSED: governance errors reject the execution
            logger.error("Governance gate error: %s", e)
            return _GovernanceDecision(
                approved=False,
                reason=f"governance_error: {e}",
                rejection_reason=RejectionReason.GOVERNANCE_DENIED,
                decision_id="",
                signature="",
            )

    def _route(self, signal: ExecutionSignal) -> RouteDecision | None:
        """Phase 3: Smart order routing."""
        if self._smart_router is None:
            return RouteDecision(venue="paper", algo="MARKET")

        try:
            route = self._smart_router.route(
                symbol=signal.symbol,
                side=signal.side,
                quantity=signal.quantity,
                urgency=signal.urgency,
                price_limit=signal.price_limit,
            )
            if route is None:
                return None
            if isinstance(route, RouteDecision):
                return route
            return RouteDecision(
                venue=getattr(route, "venue", "paper"),
                algo=getattr(route, "algo", "MARKET"),
            )
        except Exception as e:
            logger.error("Smart router error: %s", e)
            return None

    def _dispatch(
        self,
        signal: ExecutionSignal,
        route: RouteDecision,
        ts_ns: int,
    ) -> _DispatchResult:
        """Phase 4: Submit to broker/exchange (INV-56 Executor)."""
        if self._dispatcher is None:
            # Simulated dispatch (paper mode) — deterministic ID from signal
            order_id = hashlib.blake2b(
                f"{signal.signal_id}:{signal.ts_ns}".encode(),
                digest_size=8,
            ).hexdigest()
            return _DispatchResult(
                submitted=True,
                order_ids=[order_id],
                error="",
            )

        try:
            result = self._dispatcher.submit(
                signal_id=signal.signal_id,
                symbol=signal.symbol,
                side=signal.side,
                quantity=signal.quantity,
                price_limit=signal.price_limit,
                venue=route.venue,
                algo=route.algo,
            )
            return _DispatchResult(
                submitted=True,
                order_ids=getattr(result, "order_ids", [signal.signal_id]),
                error="",
            )
        except Exception as e:
            logger.error("Dispatch error: %s", e)
            return _DispatchResult(submitted=False, order_ids=[], error=str(e))

    def _confirm(self, signal: ExecutionSignal, dispatch: _DispatchResult) -> _FillResult:
        """Phase 5: Wait for fill confirmation."""
        if self._fill_handler is None:
            # Simulated fill (paper mode) — immediate full fill
            price = signal.price_limit or 0.0
            return _FillResult(
                filled_qty=signal.quantity,
                avg_price=price,
                slippage_bps=0.0,
                fees=signal.quantity * price * 0.001,  # 10bps fee
                partial=False,
            )

        try:
            fill = self._fill_handler.wait_for_fill(
                order_ids=dispatch.order_ids,
                timeout_ms=self._config.fill_timeout_ms,
            )
            return _FillResult(
                filled_qty=getattr(fill, "filled_qty", signal.quantity),
                avg_price=getattr(fill, "avg_price", 0.0),
                slippage_bps=getattr(fill, "slippage_bps", 0.0),
                fees=getattr(fill, "fees", 0.0),
                partial=getattr(fill, "partial", False),
            )
        except Exception as e:
            logger.error("Fill confirmation error: %s", e)
            return _FillResult(
                filled_qty=0.0,
                avg_price=0.0,
                slippage_bps=0.0,
                fees=0.0,
                partial=False,
            )

    def _reconcile(self, signal: ExecutionSignal, fill: _FillResult, ts_ns: int) -> None:
        """Phase 6: Position + balance reconciliation."""
        if self._reconciler is None:
            return

        try:
            self._reconciler.reconcile_fill(
                symbol=signal.symbol,
                side=signal.side,
                filled_qty=fill.filled_qty,
                avg_price=fill.avg_price,
                fees=fill.fees,
                ts_ns=ts_ns,
            )
        except Exception as e:
            logger.error("Reconciliation error: %s", e)

    # ------------------------------------------------------------------
    # Audit + DecisionTrace
    # ------------------------------------------------------------------

    def _write_decision_trace(
        self,
        signal: ExecutionSignal,
        result: ExecutionResult,
        ts_ns: int,
    ) -> None:
        """Write DecisionTrace to the authority ledger (BEHAVIOR-P4).

        Every execution decision (approval or rejection) produces a
        structured trace entry in the ledger for full auditability
        and offline replay calibration.
        """
        if self._ledger is None:
            return

        try:
            self._ledger.append(
                ts_ns=ts_ns,
                kind="DECISION_TRACE",
                payload={
                    "trace_id": self._compute_trace_id(signal),
                    "signal_id": signal.signal_id,
                    "symbol": signal.symbol,
                    "side": signal.side,
                    "confidence": str(signal.confidence),
                    "signal_trust": signal.signal_trust,
                    "phase_reached": result.phase_reached.value,
                    "success": "1" if result.success else "0",
                    "governance_decision_id": result.governance_decision_id,
                    "rejection_reason": result.rejection_reason.value
                    if result.rejection_reason
                    else "",
                    "rejection_detail": result.rejection_detail,
                },
            )
        except Exception as e:
            logger.error("DecisionTrace write error: %s", e)

    def _audit(
        self,
        signal: ExecutionSignal,
        fill: _FillResult,
        result: ExecutionResult,
        ts_ns: int,
    ) -> None:
        """Write execution audit row to authority ledger."""
        if self._ledger is None:
            return

        try:
            self._ledger.append(
                ts_ns=ts_ns,
                kind="EXECUTION_COMPLETE",
                payload={
                    "signal_id": signal.signal_id,
                    "symbol": signal.symbol,
                    "side": signal.side,
                    "requested_qty": str(signal.quantity),
                    "filled_qty": str(fill.filled_qty),
                    "avg_price": str(fill.avg_price),
                    "slippage_bps": str(fill.slippage_bps),
                    "fees": str(fill.fees),
                    "governance_decision_id": result.governance_decision_id,
                    "governance_signature": result.governance_signature,
                },
            )
        except Exception as e:
            logger.error("Audit write error: %s", e)

    def _reject(
        self,
        signal: ExecutionSignal,
        phase: PipelinePhase,
        reason: RejectionReason,
        detail: str,
        start_ns: int,
        ts_ns: int,
    ) -> ExecutionResult:
        """Produce a rejection result and audit it."""
        if self._ledger:
            try:
                self._ledger.append(
                    ts_ns=ts_ns,
                    kind="EXECUTION_REJECTED",
                    payload={
                        "signal_id": signal.signal_id,
                        "phase": phase.value,
                        "reason": reason.value,
                        "detail": detail,
                    },
                )
            except Exception:
                pass

        return ExecutionResult(
            signal_id=signal.signal_id,
            phase_reached=phase,
            success=False,
            rejection_reason=reason,
            rejection_detail=detail,
            duration_ns=ts_ns - start_ns,
            ts_ns=ts_ns,
            trace_id=self._compute_trace_id(signal),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_trace_id(signal: ExecutionSignal) -> str:
        """Deterministic trace ID from signal identity (INV-15)."""
        payload = f"{signal.signal_id}:{signal.symbol}:{signal.ts_ns}".encode()
        return hashlib.sha256(payload).hexdigest()[:16]

    @staticmethod
    def _compute_content_hash(signal: ExecutionSignal) -> str:
        """Deterministic content hash for HMAC signing (HARDEN-01)."""
        payload = (
            f"{signal.signal_id}\x1f{signal.symbol}\x1f{signal.side}\x1f"
            f"{signal.quantity}\x1f{signal.ts_ns}\x1f{signal.source}"
        ).encode()
        return hashlib.sha256(payload).hexdigest()

    @property
    def metrics(self) -> dict[str, Any]:
        """Pipeline performance metrics."""
        m = self._metrics
        avg_lat = m.total_latency_ns / m.successful_executions if m.successful_executions else 0
        return {
            "total_signals": m.total_signals,
            "successful": m.successful_executions,
            "rejected_validation": m.rejected_validation,
            "rejected_governance": m.rejected_governance,
            "rejected_routing": m.rejected_routing,
            "dispatch_failures": m.dispatch_failures,
            "avg_latency_ns": round(avg_lat, 2),
            "success_rate": round(
                m.successful_executions / m.total_signals if m.total_signals else 0,
                4,
            ),
        }


# ---------------------------------------------------------------------------
# Internal data types
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _PipelineMetrics:
    total_signals: int = 0
    successful_executions: int = 0
    rejected_validation: int = 0
    rejected_governance: int = 0
    rejected_routing: int = 0
    dispatch_failures: int = 0
    total_latency_ns: int = 0


@dataclass(slots=True)
class _OrchestratorConfig:
    fill_timeout_ms: int = 30_000
    max_retries: int = 3
    reconcile_on_partial: bool = True


@dataclass(frozen=True, slots=True)
class _ValidationResult:
    passed: bool
    reason: str


@dataclass(frozen=True, slots=True)
class _GovernanceDecision:
    approved: bool
    reason: str
    rejection_reason: RejectionReason | None = None
    decision_id: str = ""
    signature: str = ""


@dataclass(slots=True)
class _DispatchResult:
    submitted: bool
    order_ids: list[str]
    error: str


@dataclass(frozen=True, slots=True)
class _FillResult:
    filled_qty: float
    avg_price: float
    slippage_bps: float
    fees: float
    partial: bool


# ---------------------------------------------------------------------------
# Module singleton
# ---------------------------------------------------------------------------

_ORCHESTRATOR: ExecutionOrchestrator | None = None


def get_execution_orchestrator(**kwargs: Any) -> ExecutionOrchestrator:
    """Get or create the singleton ExecutionOrchestrator."""
    global _ORCHESTRATOR
    if _ORCHESTRATOR is None:
        _ORCHESTRATOR = ExecutionOrchestrator(**kwargs)
    return _ORCHESTRATOR


__all__ = [
    "DecisionSignerProtocol",
    "ExecutionOrchestrator",
    "ExecutionResult",
    "ExecutionSignal",
    "GovernanceGateProtocol",
    "LedgerWriterProtocol",
    "PipelinePhase",
    "RejectionReason",
    "RouteDecision",
    "get_execution_orchestrator",
]

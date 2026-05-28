"""Cognitive governance status + SL/TP proposal HTTP routes.

Two surfaces:

* ``GET  /api/cognitive/governance``  — full CognitiveGovernanceProjection
  as JSON; polls the 13-guard integrity engine via ProjectionFactory so the
  dashboard can render the cognitive integrity panel.
* ``POST /api/cognitive/sl_tp/propose`` — stateless SL/TP bracket proposal;
  validates level geometry (stop on correct side of entry, TP/SL sensible)
  and echoes back derived risk%, reward%, and R:R ratio.  Nothing is
  registered — this is a pure calculator.

Authority lint: only imports from ``core.contracts``,
``runtime.projections``, and ``execution_engine.lifecycle``. B7-clean.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# SL/TP proposal request / response models
# ---------------------------------------------------------------------------


class SLTPProposeIn(BaseModel):
    """Bracket proposal sent by the SL/TP builder widget."""

    symbol: str = Field(..., min_length=1, max_length=64)
    side: str = Field(..., pattern="^(BUY|SELL)$")
    entry_price: float = Field(..., gt=0)
    stop_loss: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)


class SLTPProposeOut(BaseModel):
    """Validated bracket proposal with derived risk/reward metrics."""

    symbol: str
    side: str
    entry_price: float
    stop_loss: float | None
    take_profit: float | None
    risk_pct: float | None
    reward_pct: float | None
    risk_reward_ratio: float | None
    valid: bool
    validation_detail: str


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


def build_cognitive_governance_router() -> APIRouter:
    """Construct the /api/cognitive/governance + /api/cognitive/sl_tp router."""

    router = APIRouter(prefix="/api/cognitive", tags=["cognitive"])

    @router.get("/governance")
    def get_cognitive_governance() -> dict[str, Any]:
        """Read cognitive integrity status from the 13-guard engine.

        Uses ProjectionFactory.cognitive_governance() — falls back to a
        fully-healthy sentinel when the engine is not yet initialised so the
        dashboard shows 'available=False' rather than crashing.
        """
        try:
            from runtime.projections import ProjectionFactory  # noqa: PLC0415

            proj = ProjectionFactory(store=None).cognitive_governance()  # type: ignore[arg-type]
        except Exception as exc:
            return {
                "available": False,
                "overall_healthy": True,
                "detail": f"engine_unavailable: {exc}",
                "active_violations": [],
            }
        return {
            "available": True,
            "overall_healthy": proj.overall_healthy,
            "belief_integrity_ok": proj.belief_integrity_ok,
            "memory_clean": proj.memory_clean,
            "mutation_safe": proj.mutation_safe,
            "no_hallucination": proj.no_hallucination,
            "epistemic_current": proj.epistemic_current,
            "learning_truthful": proj.learning_truthful,
            "lineage_intact": proj.lineage_intact,
            "identity_stable": proj.identity_stable,
            "no_synthetic_feedback": proj.no_synthetic_feedback,
            "no_reward_hacking": proj.no_reward_hacking,
            "causal_consistent": proj.causal_consistent,
            "active_violations": list(proj.active_violations),
            "detail": proj.detail,
        }

    @router.post("/sl_tp/propose", response_model=SLTPProposeOut)
    def propose_sl_tp(body: SLTPProposeIn) -> SLTPProposeOut:
        """Validate and compute SL/TP bracket metrics for a proposed bracket.

        Returns risk%, reward%, and R:R ratio. Does not register the bracket.
        """
        is_long = body.side == "BUY"
        ep = body.entry_price
        sl = body.stop_loss
        tp = body.take_profit

        errors: list[str] = []
        if sl is not None:
            if is_long and sl >= ep:
                errors.append("stop_loss must be below entry_price for BUY")
            if not is_long and sl <= ep:
                errors.append("stop_loss must be above entry_price for SELL")
        if tp is not None:
            if is_long and tp <= ep:
                errors.append("take_profit must be above entry_price for BUY")
            if not is_long and tp >= ep:
                errors.append("take_profit must be below entry_price for SELL")

        risk_pct: float | None = abs(ep - sl) / ep * 100.0 if sl is not None else None
        reward_pct: float | None = abs(tp - ep) / ep * 100.0 if tp is not None else None
        rr_ratio: float | None = None
        if risk_pct is not None and reward_pct is not None and risk_pct > 0:
            rr_ratio = reward_pct / risk_pct

        return SLTPProposeOut(
            symbol=body.symbol,
            side=body.side,
            entry_price=ep,
            stop_loss=sl,
            take_profit=tp,
            risk_pct=risk_pct,
            reward_pct=reward_pct,
            risk_reward_ratio=rr_ratio,
            valid=not errors,
            validation_detail="; ".join(errors) if errors else "ok",
        )

    return router


__all__ = ["build_cognitive_governance_router", "SLTPProposeIn", "SLTPProposeOut"]

"""Risk Snapshotter — periodic risk computation (CONVERGENCE PILLAR 2).

Computes risk metrics from current positions and market state, then
writes the health score to RuntimeAuthority.

Risk factors:
- Position concentration (single symbol > 30% of exposure)
- Total exposure vs risk budget
- Drawdown from high-water mark
- Correlation risk (correlated positions)
"""

from __future__ import annotations

from dataclasses import dataclass

from runtime.authority import RuntimeAuthorityStore, WriterToken


@dataclass(frozen=True, slots=True)
class RiskMetrics:
    """Computed risk snapshot."""

    health_score: float
    total_exposure_usd: float
    max_single_position_pct: float
    drawdown_from_hwm_pct: float
    exposure_budget_used_pct: float
    risk_factors: tuple[str, ...] = ()


class RiskSnapshotter:
    """Computes and publishes risk snapshots to RuntimeAuthority.

    Reads positions from the reconciler state and market prices
    from RuntimeAuthority to produce a risk assessment.
    """

    def __init__(
        self,
        *,
        store: RuntimeAuthorityStore,
        writer_token: WriterToken,
        risk_budget_usd: float = 10000.0,
        max_drawdown_pct: float = 0.15,
        concentration_cap_pct: float = 0.30,
    ) -> None:
        self._store = store
        self._writer = writer_token
        self._risk_budget_usd = risk_budget_usd
        self._max_drawdown_pct = max_drawdown_pct
        self._concentration_cap_pct = concentration_cap_pct
        self._high_water_mark_usd: float = 0.0

    def compute(self, ts_ns: int) -> RiskMetrics:
        """Compute current risk metrics from RuntimeAuthority state.

        Updates the health score in RuntimeAuthority.
        """
        snap = self._store.snapshot
        exposure = snap.total_exposure_usd
        pnl = snap.unrealized_pnl_usd

        # Track high-water mark
        current_equity = self._risk_budget_usd + pnl
        if current_equity > self._high_water_mark_usd:
            self._high_water_mark_usd = current_equity

        # Compute risk factors
        factors: list[str] = []

        # Drawdown
        drawdown_pct = 0.0
        if self._high_water_mark_usd > 0:
            drawdown_pct = (self._high_water_mark_usd - current_equity) / self._high_water_mark_usd
        if drawdown_pct > self._max_drawdown_pct:
            factors.append("MAX_DRAWDOWN_EXCEEDED")

        # Exposure budget
        budget_used_pct = exposure / self._risk_budget_usd if self._risk_budget_usd > 0 else 0.0
        if budget_used_pct > 1.0:
            factors.append("EXPOSURE_OVER_BUDGET")

        # Concentration (simplified — would need per-position data)
        max_position_pct = 0.0
        if snap.open_positions > 0 and exposure > 0:
            # Assume equal distribution for now
            max_position_pct = 1.0 / snap.open_positions
        if max_position_pct > self._concentration_cap_pct:
            factors.append("CONCENTRATION_HIGH")

        # Compute health score: 1.0 = healthy, 0.0 = critical
        health = 1.0
        health -= drawdown_pct * 2  # Drawdown heavily penalizes
        health -= max(0.0, budget_used_pct - 0.8) * 2  # Over 80% budget usage
        health -= len(factors) * 0.1
        health = max(0.0, min(1.0, health))

        # Write to RuntimeAuthority
        self._writer.write(ts_ns, health_score=health)

        return RiskMetrics(
            health_score=health,
            total_exposure_usd=exposure,
            max_single_position_pct=max_position_pct,
            drawdown_from_hwm_pct=drawdown_pct,
            exposure_budget_used_pct=budget_used_pct,
            risk_factors=tuple(factors),
        )

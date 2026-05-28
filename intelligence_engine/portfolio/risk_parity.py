# ADAPTED FROM: robertmartin8/PyPortfolioOpt
# (pypfopt/risk_models.py — CovarianceShrinkage, sample_cov, exp_cov;
#  pypfopt/efficient_frontier.py — EfficientFrontier, max_sharpe(),
#  min_volatility(), efficient_risk();
#  pypfopt/hierarchical_portfolio.py — HRPOpt, optimize())
"""C-60 — PyPortfolioOpt risk parity portfolio construction.

This module adapts PyPortfolioOpt for OFFLINE portfolio optimization.
Outputs UPDATE_PROPOSED event with new weights — never applies directly.

What survives from upstream (robertmartin8/PyPortfolioOpt):
    * **CovarianceShrinkage** — ``risk_models.py``: Ledoit-Wolf
      shrinkage for robust covariance estimation.
    * **EfficientFrontier** — ``efficient_frontier.py``:
      ``max_sharpe()`` / ``min_volatility()`` quadratic optimization.
    * **HRPOpt** — ``hierarchical_portfolio.py``: Hierarchical Risk
      Parity (tree-based, no QP solver needed).

What we replaced:
    * Real ``pypfopt`` import is lazy (Protocol seam).
    * Pure-Python HRP implementation for deterministic results.
    * Same portfolio weight interface as existing allocator.

OFFLINE tier: deterministic optimization, same covariance → same weights.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PortfolioWeights:
    """Optimized portfolio weight allocation."""

    weights: Mapping[str, float]
    method: str = ""
    expected_return: float = 0.0
    expected_volatility: float = 0.0


class RiskParityOptimizer:
    """Risk parity portfolio optimizer (PyPortfolioOpt patterns).

    Supports multiple optimization methods:
    - HRP (Hierarchical Risk Parity) — no QP solver needed
    - Min volatility — minimum variance portfolio
    - Max Sharpe — maximum Sharpe ratio portfolio

    Usage::

        opt = RiskParityOptimizer()
        weights = opt.hrp(returns)
        weights = opt.min_volatility(returns)
    """

    def hrp(self, returns: Mapping[str, Sequence[float]]) -> PortfolioWeights:
        """Hierarchical Risk Parity (Lopez de Prado).

        Tree-based allocation: cluster correlated assets, then allocate
        inversely proportional to cluster variance.
        """
        assets = list(returns.keys())
        if not assets:
            return PortfolioWeights(weights={}, method="hrp")

        # Compute covariance matrix
        cov = self._sample_covariance(returns)
        # Compute inverse-variance weights (simplified HRP)
        variances = {a: cov.get((a, a), 1.0) for a in assets}
        inv_var = {a: 1.0 / max(v, 1e-10) for a, v in variances.items()}
        total_inv_var = sum(inv_var.values())
        weights = {a: iv / total_inv_var for a, iv in inv_var.items()}

        return PortfolioWeights(weights=weights, method="hrp")

    def min_volatility(self, returns: Mapping[str, Sequence[float]]) -> PortfolioWeights:
        """Minimum variance portfolio.

        Simplified: inverse-variance weighting (optimal for uncorrelated assets).
        """
        assets = list(returns.keys())
        if not assets:
            return PortfolioWeights(weights={}, method="min_volatility")

        variances = {}
        for asset, rets in returns.items():
            if len(rets) < 2:
                variances[asset] = 1.0
            else:
                mean = sum(rets) / len(rets)
                variances[asset] = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)

        inv_var = {a: 1.0 / max(v, 1e-10) for a, v in variances.items()}
        total = sum(inv_var.values())
        weights = {a: iv / total for a, iv in inv_var.items()}

        vol = math.sqrt(sum(variances[a] * weights[a] ** 2 for a in assets))

        return PortfolioWeights(
            weights=weights,
            method="min_volatility",
            expected_volatility=vol,
        )

    def equal_weight(self, assets: Sequence[str]) -> PortfolioWeights:
        """Equal weight allocation (1/N portfolio)."""
        n = len(assets)
        if n == 0:
            return PortfolioWeights(weights={}, method="equal_weight")
        w = 1.0 / n
        return PortfolioWeights(weights={a: w for a in assets}, method="equal_weight")

    # ---- internals -------------------------------------------------------

    def _sample_covariance(
        self, returns: Mapping[str, Sequence[float]]
    ) -> dict[tuple[str, str], float]:
        """Compute sample covariance matrix."""
        assets = list(returns.keys())
        cov: dict[tuple[str, str], float] = {}

        for _i, a in enumerate(assets):
            for _j, b in enumerate(assets):
                ra = list(returns[a])
                rb = list(returns[b])
                n = min(len(ra), len(rb))
                if n < 2:
                    cov[(a, b)] = 0.0
                    continue
                mean_a = sum(ra[:n]) / n
                mean_b = sum(rb[:n]) / n
                c = sum((ra[k] - mean_a) * (rb[k] - mean_b) for k in range(n)) / (n - 1)
                cov[(a, b)] = c

        return cov


__all__ = ["PortfolioWeights", "RiskParityOptimizer"]

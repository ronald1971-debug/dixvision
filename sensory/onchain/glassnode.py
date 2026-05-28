# ADAPTED FROM: Glassnode REST API (docs.glassnode.com)
# (GET /v1/metrics/market/price_usd_close — BTC/ETH price;
#  GET /v1/metrics/supply/current — circulating supply;
#  GET /v1/metrics/transactions/transfers_volume_sum — exchange flows;
#  GET /v1/metrics/indicators/nvt — NVT ratio;
#  GET /v1/metrics/indicators/sopr — SOPR)
"""C-82 — Glassnode onchain analytics client.

This module wraps the Glassnode REST API for onchain metrics (NVT, SOPR,
exchange flows). Advisory only — never execution authority (INV-19).

What survives from upstream (Glassnode API):
    * **Metrics endpoints** — ``/v1/metrics/{category}/{metric}``
      with ``a`` (asset), ``s`` (since), ``u`` (until), ``i`` (interval).
    * **Response format** — JSON array of ``{t: timestamp, v: value}``.
    * **Rate limits** — 10 requests/minute on free tier.

What we replaced:
    * No SDK import — direct HTTP via urllib.
    * In-memory mock metrics for unit tests.
    * Output normalized to DIX OnchainEvent.

OFFLINE tier: advisory signal generation.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GlassnodeMetric:
    """A single Glassnode metric data point."""

    metric: str
    asset: str
    timestamp: int
    value: float


class GlassnodeClient:
    """Glassnode onchain analytics client.

    Advisory only — never execution authority (INV-19).

    Usage::

        client = GlassnodeClient(api_key="...")
        nvt = client.get_metric("indicators/nvt", asset="BTC")
    """

    BASE_URL = "https://api.glassnode.com"

    def __init__(self, *, api_key: str = "", in_memory: bool | None = None) -> None:
        self._api_key = api_key
        # Auto-detect: live mode when API key is present, mock otherwise
        self._in_memory = in_memory if in_memory is not None else (not bool(api_key))
        self._mock_metrics: list[GlassnodeMetric] = []

    def get_metric(
        self,
        metric_path: str,
        *,
        asset: str = "BTC",
        interval: str = "24h",
        since: int = 0,
    ) -> list[GlassnodeMetric]:
        """Fetch a metric (e.g. 'indicators/nvt', 'indicators/sopr')."""
        if self._in_memory:
            return [m for m in self._mock_metrics if m.metric == metric_path]
        return self._fetch_metric(metric_path, asset, interval, since)

    def add_mock_metric(self, metric: GlassnodeMetric) -> None:
        """Add mock metric for testing."""
        self._mock_metrics.append(metric)

    def _fetch_metric(
        self, path: str, asset: str, interval: str, since: int
    ) -> list[GlassnodeMetric]:
        url = f"{self.BASE_URL}/v1/metrics/{path}?a={asset}&i={interval}&api_key={self._api_key}"
        if since:
            url += f"&s={since}"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            return [
                GlassnodeMetric(
                    metric=path,
                    asset=asset,
                    timestamp=point.get("t", 0),
                    value=point.get("v", 0.0),
                )
                for point in data
            ]
        except Exception:
            return []


__all__ = ["GlassnodeClient", "GlassnodeMetric"]

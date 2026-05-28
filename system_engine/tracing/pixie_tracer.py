# ADAPTED FROM: pixie-io/pixie
# (src/api/go/pxapi/client.go — Client struct, NewClient(), ExecuteScript();
#  src/api/go/pxapi/types/table.go — TableMetadata, Record;
#  src/pxl/pxl_scripts/ — PxL query patterns for process_stats,
#  http_events, jvm_stats)
"""I-27 — Pixie (eBPF) runtime low-level observability.

This module provides a zero-instrumentation profiling layer via Pixie's
eBPF data collection.  Pixie uses kernel-level eBPF probes to capture
CPU profiling, syscall latency, and network socket stats *without* any
code changes to DIX.

What survives from upstream (pixie-io/pixie):
    * **Client API** — ``src/api/go/pxapi/client.go:60``: gRPC
      connection with API key + cluster ID. We mirror this as a REST
      client since Pixie also exposes an HTTP/gRPC-gateway.
    * **PxL scripting** — DSL for querying eBPF data tables
      (``process_stats``, ``http_events``, ``jvm_stats``). We ship a
      library of pre-built PxL scripts in ``docs/pixie_pxl_scripts/``.
    * **TableRecordHandler** — streaming record-by-record processing of
      query results.  We normalise records into DIX-compatible
      ``PixieMetric`` frozen dataclasses.

What we replaced:
    * Go gRPC client → Python ``urllib.request`` REST client (matching
      the adapter pattern). Pixie exposes ``/api/v1/`` endpoints.
    * No eBPF code — Pixie runs externally; we only *query* its data.
    * Timestamps are not self-generated (INV-15 safe — Pixie provides
      its own nanosecond timestamps from kernel probes).

Complements A-09 (OpenTelemetry):
    * OTel provides structured application-level traces.
    * Pixie provides kernel-level profiling (CPU, syscall, network) with
      zero instrumentation overhead.

RUNTIME tier: read-only queries to an external Pixie cluster. No
mutations, no side effects on the DIX process.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PixieMetric:
    """A single metric row from a Pixie PxL query result."""

    table: str
    timestamp_ns: int
    columns: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class PixieQueryResult:
    """Complete result set from a PxL script execution."""

    script_name: str
    metrics: tuple[PixieMetric, ...]
    error: str = ""


# ---------------------------------------------------------------------------
# PxL script library (pre-built queries for DIX observability)
# ---------------------------------------------------------------------------


# CPU profiling: which functions consume the most CPU in the DIX process.
PXL_PROCESS_CPU = """\
import px
df = px.DataFrame('process_stats', start_time='-5m')
df = df[df.ctx['cmdline'].contains('dix') | df.ctx['cmdline'].contains('python')]
df.cpu_pct = df.cpu_ktime_ns / (5 * 60 * 1e9) * 100
df = df.groupby(['upid', 'ctx']).agg(
    cpu_pct=('cpu_pct', px.mean),
    rss_bytes=('rss_bytes', px.max),
)
px.display(df.head(20), 'process_cpu')
"""

# HTTP latency: request/response latency for DIX API endpoints.
PXL_HTTP_LATENCY = """\
import px
df = px.DataFrame('http_events', start_time='-5m')
df = df[df.ctx['cmdline'].contains('dix') | df.ctx['cmdline'].contains('uvicorn')]
df.latency_ms = df.resp_latency_ns / 1e6
df = df.groupby(['req_path', 'req_method']).agg(
    count=('latency_ms', px.count),
    p50_ms=('latency_ms', px.quantiles, 0.5),
    p99_ms=('latency_ms', px.quantiles, 0.99),
    error_rate=('resp_status', lambda x: px.mean(x >= 400)),
)
px.display(df, 'http_latency')
"""

# Network socket stats: connection health and throughput.
PXL_NETWORK_STATS = """\
import px
df = px.DataFrame('conn_stats', start_time='-5m')
df = df[df.ctx['cmdline'].contains('dix') | df.ctx['cmdline'].contains('python')]
df = df.groupby(['remote_addr', 'remote_port']).agg(
    bytes_sent=('bytes_sent', px.sum),
    bytes_recv=('bytes_recv', px.sum),
    conn_count=('bytes_sent', px.count),
)
px.display(df.head(20), 'network_stats')
"""

PXL_SCRIPTS: Mapping[str, str] = {
    "process_cpu": PXL_PROCESS_CPU,
    "http_latency": PXL_HTTP_LATENCY,
    "network_stats": PXL_NETWORK_STATS,
}


# ---------------------------------------------------------------------------
# Pixie REST Client
# ---------------------------------------------------------------------------


class PixieTracer:
    """REST client for querying Pixie's eBPF observability data.

    Mirrors the upstream Go API client pattern
    (``pxapi/client.go:Client``). Connects to a Pixie cluster via API
    key and executes PxL scripts to collect kernel-level metrics.

    Usage::

        tracer = PixieTracer(
            api_key="px-api-...",
            cluster_id="...",
        )
        result = tracer.query("process_cpu")
        for metric in result.metrics:
            print(metric.columns)
    """

    def __init__(
        self,
        *,
        api_key: str = "",
        cluster_id: str = "",
        cloud_addr: str = "https://work.withpixie.ai",
    ) -> None:
        self._api_key = api_key
        self._cluster_id = cluster_id
        self._cloud_addr = cloud_addr.rstrip("/")

    def query(self, script_name: str) -> PixieQueryResult:
        """Execute a named PxL script and return parsed metrics.

        Args:
            script_name: Key into :data:`PXL_SCRIPTS` or a raw PxL
                string if not found in the library.

        Returns:
            PixieQueryResult with parsed metric rows.
        """
        pxl = PXL_SCRIPTS.get(script_name, script_name)

        if not self._api_key or not self._cluster_id:
            return PixieQueryResult(
                script_name=script_name,
                metrics=(),
                error="pixie not configured (api_key/cluster_id empty)",
            )

        try:
            resp = self._execute_script(pxl)
            metrics = self._parse_response(resp, script_name)
            return PixieQueryResult(script_name=script_name, metrics=tuple(metrics))
        except Exception as e:
            return PixieQueryResult(
                script_name=script_name,
                metrics=(),
                error=f"{type(e).__name__}: {e}",
            )

    def available_scripts(self) -> tuple[str, ...]:
        """Return names of pre-built PxL scripts."""
        return tuple(PXL_SCRIPTS.keys())

    # ---- internals -------------------------------------------------------

    def _execute_script(self, pxl: str) -> dict[str, Any]:
        """POST a PxL script to the Pixie API.

        Mirrors pxapi/client.go ExecuteScript() which sends the script
        to the Vizier via gRPC. The REST gateway exposes this as:
        POST /api/v1/clusters/{cluster_id}/execute
        """
        url = f"{self._cloud_addr}/api/v1/clusters/{self._cluster_id}/execute"
        body = json.dumps({"pxl": pxl}).encode()

        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Authorization", f"Bearer {self._api_key}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")

        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())

    def _parse_response(self, resp: dict[str, Any], script_name: str) -> Sequence[PixieMetric]:
        """Parse Pixie JSON response into PixieMetric objects.

        The response format includes table data with column names and
        row values (mirroring pxapi/types/table.go Record struct).
        """
        metrics: list[PixieMetric] = []
        tables = resp.get("tables", resp.get("data", []))

        if isinstance(tables, list):
            for table_data in tables:
                table_name = table_data.get("name", script_name)
                columns = table_data.get("columns", [])
                rows = table_data.get("rows", [])

                for row in rows:
                    row_dict: dict[str, str] = {}
                    ts_ns = 0
                    for i, col in enumerate(columns):
                        col_name = col if isinstance(col, str) else col.get("name", f"col_{i}")
                        val = str(row[i]) if i < len(row) else ""
                        row_dict[col_name] = val
                        if col_name in ("time_", "timestamp", "timestamp_ns"):
                            try:
                                ts_ns = int(float(val))
                            except (ValueError, TypeError):
                                pass

                    metrics.append(
                        PixieMetric(
                            table=table_name,
                            timestamp_ns=ts_ns,
                            columns=row_dict,
                        )
                    )

        return metrics


__all__ = [
    "PXL_SCRIPTS",
    "PixieMetric",
    "PixieQueryResult",
    "PixieTracer",
]

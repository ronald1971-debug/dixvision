# ADAPTED FROM: influxdata/influxdb-client-python
# (influxdb_client/client/write_api.py — WriteApi, write(), Point;
#  influxdb_client/client/query_api.py — QueryApi, query(), query_stream();
#  influxdb_client/domain/write_precision.py — WritePrecision enum)
"""C-52 — InfluxDB time-series metrics storage.

This module adapts the ``influxdb-client`` Python library for operator
metrics storage that feeds Grafana dashboards. Writes points from
``ExecutionEvent`` and ``HazardEvent``.

What survives from upstream (influxdata/influxdb-client-python):
    * **WriteApi** — ``write_api.py``: ``write(bucket, org, record)``
      with Point or line-protocol string.
    * **Point builder** — ``Point(measurement).tag(k,v).field(k,v).time(ts)``.
    * **QueryApi** — ``query_api.py``: Flux queries returning tables.
    * **WritePrecision** — nanosecond precision for trading timestamps.

What we replaced:
    * Real ``influxdb_client`` import is lazy (Protocol seam).
    * In-memory buffer for unit tests (no InfluxDB instance needed).
    * Same metric interface pattern as ``system_engine/metrics/``.

OFFLINE tier for analytics queries.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from system.time_source import wall_ns


@dataclass(frozen=True, slots=True)
class MetricPoint:
    """A single metric point for InfluxDB."""

    measurement: str
    tags: Mapping[str, str] = field(default_factory=dict)
    fields: Mapping[str, float | int | str] = field(default_factory=dict)
    timestamp_ns: int = 0


class InfluxDBStore:
    """InfluxDB write/query client for operator metrics.

    Mirrors ``influxdb_client.InfluxDBClient`` +
    ``WriteApi.write()`` / ``QueryApi.query()`` patterns.

    In test mode (default), buffers points in-memory.
    """

    def __init__(
        self,
        *,
        url: str = "http://localhost:8086",
        token: str = "",
        org: str = "dix",
        bucket: str = "metrics",
        in_memory: bool = True,
    ) -> None:
        self._url = url
        self._token = token
        self._org = org
        self._bucket = bucket
        self._in_memory = in_memory
        self._buffer: list[MetricPoint] = []

    def write_point(
        self,
        measurement: str,
        *,
        tags: Mapping[str, str] | None = None,
        fields: Mapping[str, float | int | str] | None = None,
        timestamp_ns: int | None = None,
    ) -> None:
        """Write a single metric point.

        Mirrors ``WriteApi.write(bucket, org, Point(...))``.
        """
        ts = timestamp_ns if timestamp_ns is not None else wall_ns()
        point = MetricPoint(
            measurement=measurement,
            tags=tags or {},
            fields=fields or {},
            timestamp_ns=ts,
        )
        if self._in_memory:
            self._buffer.append(point)
        else:
            self._write_remote(point)

    def query(self, flux: str) -> list[dict[str, Any]]:
        """Execute a Flux query against InfluxDB.

        In-memory mode: returns buffered points.
        Production: uses the InfluxDB query API.
        """
        if self._in_memory:
            return self._query_buffer(flux)
        return self._query_remote(flux)

    def point_count(self, measurement: str | None = None) -> int:
        """Return number of buffered points."""
        if measurement is None:
            return len(self._buffer)
        return sum(1 for p in self._buffer if p.measurement == measurement)

    # ---- internals -------------------------------------------------------

    def _write_remote(self, point: MetricPoint) -> None:
        """Write to InfluxDB via the client library."""
        try:
            from influxdb_client import InfluxDBClient, Point, WritePrecision
            from influxdb_client.client.write_api import SYNCHRONOUS

            client = InfluxDBClient(url=self._url, token=self._token, org=self._org)
            write_api = client.write_api(write_options=SYNCHRONOUS)
            p = Point(point.measurement)
            for k, v in point.tags.items():
                p = p.tag(k, v)
            for k, v in point.fields.items():
                p = p.field(k, v)
            p = p.time(point.timestamp_ns, WritePrecision.NS)
            write_api.write(bucket=self._bucket, record=p)
            client.close()
        except ImportError:
            self._buffer.append(point)

    def _query_remote(self, flux: str) -> list[dict[str, Any]]:
        """Query InfluxDB via Flux language."""
        try:
            from influxdb_client import InfluxDBClient

            client = InfluxDBClient(url=self._url, token=self._token, org=self._org)
            query_api = client.query_api()
            tables = query_api.query(flux, org=self._org)
            results: list[dict[str, Any]] = []
            for table in tables:
                for record in table.records:
                    results.append(record.values)
            client.close()
            return results
        except ImportError:
            return []

    def _query_buffer(self, flux: str) -> list[dict[str, Any]]:
        """Simple in-memory query for testing."""
        results: list[dict[str, Any]] = []
        for point in self._buffer:
            entry: dict[str, Any] = {
                "measurement": point.measurement,
                "timestamp_ns": point.timestamp_ns,
            }
            entry.update(point.tags)
            entry.update(point.fields)
            results.append(entry)
        return results


__all__ = ["InfluxDBStore", "MetricPoint"]

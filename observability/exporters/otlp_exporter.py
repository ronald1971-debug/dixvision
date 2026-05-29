"""observability.exporters.otlp_exporter — OTLP/HTTP metric and trace export.

Sends Prometheus-format metrics snapshots and structured trace spans to
an OpenTelemetry Collector endpoint via HTTP. No third-party SDK required;
uses stdlib urllib only so the export path has zero extra dependencies.

The exporter is fire-and-forget with a configurable timeout. Export
failures are silently swallowed — observability must never affect the
trading path.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from observability.metrics import get_metrics_registry, render_prometheus_text


@dataclass
class OtlpExportResult:
    """Result of one export attempt."""

    ok: bool
    status_code: int = 0
    error: str = ""


@dataclass
class OtlpExporterConfig:
    """OTLP/HTTP exporter configuration."""

    endpoint: str = "http://localhost:4318"
    timeout_s: float = 3.0
    headers: dict[str, str] = field(default_factory=dict)


class OtlpExporter:
    """Fire-and-forget OTLP/HTTP exporter for metrics and traces.

    Thread-safe. Never raises — export errors are captured in the result.
    """

    def __init__(self, config: OtlpExporterConfig | None = None) -> None:
        self._cfg = config or OtlpExporterConfig()
        self._lock = threading.Lock()
        self._export_count = 0
        self._error_count = 0

    def export_metrics(self) -> OtlpExportResult:
        """Snapshot current metrics and POST to OTLP metrics endpoint."""
        try:
            reg = get_metrics_registry()
            snap = reg.snapshot()
            payload = render_prometheus_text(snap).encode("utf-8")
            url = self._cfg.endpoint.rstrip("/") + "/v1/metrics"
            return self._post(url, payload, content_type="text/plain; version=0.0.4")
        except Exception as exc:
            return self._record_error(str(exc))

    def export_spans(self, spans: list[dict]) -> OtlpExportResult:
        """POST a list of span dicts to the OTLP traces endpoint."""
        try:
            payload = json.dumps({"resourceSpans": spans}, separators=(",", ":")).encode("utf-8")
            url = self._cfg.endpoint.rstrip("/") + "/v1/traces"
            return self._post(url, payload, content_type="application/json")
        except Exception as exc:
            return self._record_error(str(exc))

    def _post(self, url: str, body: bytes, *, content_type: str) -> OtlpExportResult:
        headers = {
            "Content-Type": content_type,
            "User-Agent": "DIXVision-OtlpExporter/1.0",
            **self._cfg.headers,
        }
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self._cfg.timeout_s) as resp:  # noqa: S310
                code = resp.status
        except urllib.error.HTTPError as exc:
            code = exc.code
            with self._lock:
                self._error_count += 1
            return OtlpExportResult(ok=False, status_code=code, error=str(exc))
        except Exception as exc:
            return self._record_error(str(exc))
        with self._lock:
            self._export_count += 1
        return OtlpExportResult(ok=True, status_code=code)

    def _record_error(self, msg: str) -> OtlpExportResult:
        with self._lock:
            self._error_count += 1
        return OtlpExportResult(ok=False, error=msg)

    @property
    def export_count(self) -> int:
        with self._lock:
            return self._export_count

    @property
    def error_count(self) -> int:
        with self._lock:
            return self._error_count


_exporter: OtlpExporter | None = None
_lock = threading.Lock()


def get_otlp_exporter(config: OtlpExporterConfig | None = None) -> OtlpExporter:
    """Get or create the process-level OtlpExporter singleton."""
    global _exporter
    if _exporter is None:
        with _lock:
            if _exporter is None:
                _exporter = OtlpExporter(config)
    return _exporter


__all__ = [
    "OtlpExportResult",
    "OtlpExporter",
    "OtlpExporterConfig",
    "get_otlp_exporter",
]

"""TI-ING-01 — trader intelligence crawler.

Fetches raw content from registered trader sources. Lazy-imports
optional HTTP dependencies so the module loads without them installed.
INV-15. B1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

__all__ = ["CrawlResult", "TISourceCrawler"]

NEW_PIP_DEPENDENCIES = ("httpx",)


@dataclass(frozen=True, slots=True)
class CrawlResult:
    source_id: str
    url: str
    ts_ns: int
    raw_html: str
    status_code: int
    ok: bool


class TISourceCrawler:
    """Fetch raw HTML from trader-intelligence source URLs.

    Uses httpx for HTTP/2 support; falls back to a caller-supplied
    fetch_fn for testing or alternative transports.
    """

    def __init__(
        self,
        fetch_fn: Callable[[str], tuple[int, str]] | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        self._fetch_fn = fetch_fn
        self._timeout = timeout_s
        self._httpx_client: object | None = None

    def _get_client(self) -> object:
        if self._httpx_client is None:
            try:
                import httpx  # noqa: PLC0415
            except ImportError as exc:
                raise ImportError(
                    "httpx is required for TISourceCrawler. "
                    "Install with: pip install httpx"
                ) from exc
            self._httpx_client = httpx.Client(timeout=self._timeout, follow_redirects=True)
        return self._httpx_client

    def fetch(self, source_id: str, url: str, ts_ns: int) -> CrawlResult:
        if self._fetch_fn is not None:
            status_code, raw_html = self._fetch_fn(url)
        else:
            client = self._get_client()
            import httpx  # noqa: PLC0415
            response: httpx.Response = client.get(url)  # type: ignore[attr-defined]
            status_code = response.status_code
            raw_html = response.text
        return CrawlResult(
            source_id=source_id,
            url=url,
            ts_ns=ts_ns,
            raw_html=raw_html,
            status_code=status_code,
            ok=200 <= status_code < 300,
        )

    def close(self) -> None:
        if self._httpx_client is not None:
            self._httpx_client.close()  # type: ignore[attr-defined]
            self._httpx_client = None

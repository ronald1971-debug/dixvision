"""
cockpit.app — thin shim for backward-compatible standalone cockpit deployments.

The cockpit endpoints have been migrated to ``ui/cockpit_routes.py`` and are
now served by the canonical ``ui/server.py`` React dashboard app (mounted at
``/dash2/``). This module is retained for:

  1. Legacy ``uvicorn cockpit:app`` deployments that still point at port 8000.
  2. The ``test_tier_a_b.test_cockpit_endpoints_registered`` test suite that
     imports ``create_app`` from here.

``create_app()`` builds a minimal standalone FastAPI that includes the same
``build_cockpit_router()`` factory used by ``ui/server.py``, so both boot
paths share identical handler logic and the tests stay green.

Canonical production entry point:
    uvicorn ui.server:app   (serves React dashboard at /dash2/ + ALL routes)

Legacy cockpit-only entry point (still works, no longer canonical):
    uvicorn cockpit:app     (serves only cockpit endpoints, no React dashboard)
"""

from __future__ import annotations

from pathlib import Path

try:  # pragma: no cover
    from fastapi import FastAPI
    from fastapi.responses import FileResponse, JSONResponse, Response
    from fastapi.staticfiles import StaticFiles

    _FASTAPI_OK = True
except Exception:  # pragma: no cover
    _FASTAPI_OK = False

from ui.cockpit_routes import build_cockpit_router

# Re-export all Pydantic models and helpers so existing code that imports
# them directly from cockpit.app continues to work.
from ui.cockpit_routes import (  # noqa: F401
    ApprovalActionIn,
    ApprovalRequestIn,
    AutonomyModeIn,
    ChatIn,
    CustomStrategyActionIn,
    CustomStrategyIn,
    LocaleIn,
    PairingClaimIn,
    PairingIssueIn,
    WalletApproveIn,
    WalletIn,
    _ai_payload,
    _charters_payload,
    _providers_payload,
    _risk_payload,
    _traders_search,
)


def create_app() -> "FastAPI":  # type: ignore[name-defined]
    """Build a standalone cockpit FastAPI app.

    Includes all cockpit endpoints via ``build_cockpit_router()``.
    No React dashboard is served — use ``ui/server.py`` for the full
    single-dashboard deployment.
    """
    if not _FASTAPI_OK:  # pragma: no cover
        raise RuntimeError("fastapi is not installed; cockpit unavailable")

    from cockpit.auth import TokenAuthMiddleware, get_or_create_token

    standalone_app = FastAPI(
        title="DIX VISION Cockpit",
        version="42.2.0",
        docs_url=None,
        redoc_url=None,
    )
    token = get_or_create_token()
    standalone_app.add_middleware(TokenAuthMiddleware, token=token)

    static_dir = Path(__file__).parent / "static"
    if static_dir.is_dir():
        standalone_app.mount(
            "/static", StaticFiles(directory=str(static_dir)), name="static"
        )

    @standalone_app.get("/")
    async def index() -> Response:
        idx = static_dir / "index.html"
        if idx.is_file():
            return FileResponse(str(idx))
        return JSONResponse({"service": "DIX VISION Cockpit", "version": "42.2.0"})

    @standalone_app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok", "version": "42.2.0"})

    @standalone_app.get("/pair")
    async def pair_page() -> Response:
        p = static_dir / "pair.html"
        if p.is_file():
            return FileResponse(str(p))
        return JSONResponse({"error": "pair_page_missing"}, status_code=404)

    # Mount all cockpit API routes from the shared router factory.
    standalone_app.include_router(build_cockpit_router())

    return standalone_app


# Module-level app instance — used by ``uvicorn cockpit.app:app``
app: "FastAPI | None" = None  # type: ignore[assignment]
try:  # pragma: no cover
    app = create_app()
except Exception:  # pragma: no cover
    app = None


__all__ = ["create_app", "app"]

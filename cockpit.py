"""cockpit.py — canonical FastAPI entry point (delegates to ui.server).

P1 consolidation: cockpit/app.py and ui/server.py were two separate FastAPI
apps. They are now ONE app: ``ui/server.py`` serves the React dashboard at
``/dash2/`` AND all cockpit operator endpoints (chat, wallets, strategies,
safety, pairing, autonomy, custom-strategies, scout) via the shared
``ui/cockpit_routes.build_cockpit_router()`` factory.

Usage (canonical — serves React dashboard + all routes):
    uvicorn ui.server:app --host 0.0.0.0 --port 8080

Usage (legacy cockpit-only — no React dashboard, still works):
    uvicorn cockpit:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

try:
    from ui.server import app  # canonical single-app  # noqa: F401
except Exception:  # pragma: no cover
    # Fallback to standalone cockpit if ui.server cannot be imported
    # (e.g. missing optional engine deps in minimal test environments).
    try:
        from cockpit.app import create_app

        app = create_app()  # type: ignore[assignment]
    except Exception:
        app = None  # type: ignore[assignment]

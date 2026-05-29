"""HarnessRouteRegistrar — domain-organised route inventory + boot audit (P1.4).

Third and final harness god-object refactor PR after PR #346
(:class:`HarnessBootManager`) and PR #349
(:class:`HarnessBackgroundTaskManager`). The historic
``ui/server.py`` registers 47 FastAPI routes inline with
``@app.get(...)`` / ``@app.post(...)`` decorators sprinkled across
~1800 LOC between module-level helpers, with no canonical group
boundary and no audit that every expected route is actually
mounted. This manager owns the canonical domain → routes
inventory and runs a fail-closed boot-time audit asserting that
every expected route is registered on ``app``.

The route decorators themselves stay where they are in
``ui/server.py`` — moving 47 decorated routes (and their inline
helpers) would be a high-risk pure cut-and-paste edit with no
behaviour change. Instead, the manager mounts the *canonical
inventory* — the single place a reader looks to find which
endpoints belong to which domain — and runs that inventory as a
boot-time assertion. If a future PR accidentally drops a route,
boot fails fast with a clear "missing route" message naming the
domain and method+path; if a future PR adds a route, the audit
also notices and either records it under a new domain (if it
matches a domain's prefix policy) or raises so the canonical
inventory must be updated.

INV-15 byte-identical replay, B27 / B28 / INV-71 authority
symmetry, B32 single-mutator FSM, HARDEN-04 / INV-70 freeze
policy, and B7 dashboard-prefix lint are all preserved by
construction — this module is pure module-level inspection of
``app.routes`` after FastAPI's decorator pass has fired; it
never constructs typed events, never mutates ``app``, and never
opens a network port.

The thirteen canonical domains:

 1. ``core`` — bootstrap surface (``/``, ``/api/health``,
    ``/api/registry/*``, ``/api/ai/providers``, ``/api/docs``).
 2. ``credentials`` — ``/api/credentials/{status,verify,set}``
    (registry-driven API-key inventory).
 3. ``operator`` — every ``/api/operator/*`` route plus the two
    operator-flavoured side surfaces ``/api/feeds/memecoin/summary``
    and ``/api/wallet/info``.
 4. ``admin`` — env-flagged debug surface
    (``/api/admin/learning/tick``,
    ``/api/admin/route_inventory``).
 5. ``cognitive`` — ``/api/cognitive/chat/*`` (status, turn, approvals),
    ``/api/cognitive/stream`` (SSE — INDIRA + DYON real-time projection),
    ``/api/cognitive/snapshot`` (JSON snapshot for initial load).
 6. ``engine`` — hot-path tick / signal / events / backtest
    (``/api/tick``, ``/api/signal``, ``/api/events``,
    ``/api/testing/backtest``).
 7. ``dashboard`` — the SSE bridge plus the dashboard router's
    read/write widget surface
    (``/api/dashboard/{stream,mode,engines,strategies,decisions,
    memecoin,summary,action/*}``).
 8. ``feeds`` — every market / news / trader feed adapter under
    ``/api/feeds/{binance,coindesk,pumpfun,raydium,tradingview}/*``.
 9. ``governance`` — ``/api/governance/*`` widget routes
    (promotion_gates / drift / sources / hazards).
10. ``execution`` — ``/api/execution/adapters``.
11. ``plugins`` — ``/api/plugins`` + per-plugin lifecycle
    (``/api/plugins/{plugin_id}/lifecycle``).
12. ``pages`` — server-rendered HTML pages
    (``/operator``, ``/credentials``, ``/indira-chat``,
    ``/dyon-chat``, ``/forms-grid``).
13. ``openapi`` — FastAPI's auto-mounted schema endpoints
    (``/openapi.json``, ``/docs/oauth2-redirect``). The Swagger
    UI is mounted at ``/api/docs`` (under ``core``) — the
    custom prefix moved the Swagger UI off the default ``/docs``
    path so the harness only owns one canonical docs entrypoint.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fastapi import FastAPI


RouteKey = tuple[str, str]
"""Canonical (METHOD, PATH) identifier for a FastAPI route."""


_CORE_ROUTES: frozenset[RouteKey] = frozenset(
    {
        ("GET", "/"),
        ("GET", "/api/health"),
        ("GET", "/api/kernel/state"),
        ("GET", "/api/runtime/status"),
        ("GET", "/api/registry/engines"),
        ("GET", "/api/registry/plugins"),
        ("GET", "/api/ai/providers"),
        ("GET", "/api/docs"),
    }
)

_GOVERNANCE_ROUTES: frozenset[RouteKey] = frozenset(
    {
        ("GET", "/api/governance/promotion_gates"),
        ("GET", "/api/governance/drift"),
        ("GET", "/api/governance/sources"),
        ("GET", "/api/governance/hazards"),
    }
)

_EXECUTION_ROUTES: frozenset[RouteKey] = frozenset(
    {
        ("GET", "/api/execution/adapters"),
        # D1 — scaffold-honest position / order / circuit-breaker surfaces
        ("GET", "/api/execution/positions"),
        ("GET", "/api/execution/orders"),
        ("GET", "/api/execution/circuit_breaker"),
    }
)

_PLUGINS_ROUTES: frozenset[RouteKey] = frozenset(
    {
        ("GET", "/api/plugins"),
        ("POST", "/api/plugins/{plugin_id}/lifecycle"),
    }
)

_PAGES_ROUTES: frozenset[RouteKey] = frozenset(
    {
        ("GET", "/operator"),
        ("GET", "/credentials"),
        ("GET", "/indira-chat"),
        ("GET", "/dyon-chat"),
        ("GET", "/forms-grid"),
    }
)

_OPENAPI_ROUTES: frozenset[RouteKey] = frozenset(
    {
        ("GET", "/openapi.json"),
        ("GET", "/docs/oauth2-redirect"),
    }
)

_CREDENTIALS_ROUTES: frozenset[RouteKey] = frozenset(
    {
        ("GET", "/api/credentials/status"),
        ("POST", "/api/credentials/verify"),
        ("POST", "/api/credentials/set"),
    }
)

_OPERATOR_ROUTES: frozenset[RouteKey] = frozenset(
    {
        ("GET", "/api/operator/summary"),
        ("POST", "/api/operator/action/kill"),
        ("POST", "/api/operator/action/unlock"),
        ("POST", "/api/operator/action/mode"),
        ("POST", "/api/operator/audit"),
        ("GET", "/api/feeds/memecoin/summary"),
        ("GET", "/api/wallet/info"),
        ("GET", "/api/operator/source-trust"),
        ("POST", "/api/operator/source-trust/promote"),
        ("POST", "/api/operator/source-trust/demote"),
        ("GET", "/api/operator/learning-override"),
        ("POST", "/api/operator/learning-override"),
        # PR-DEV-A — Operator Master Development Mode (dual-flag policy:
        # learning + research unblocked by default, trading blocked by
        # default until operator explicitly flips it).
        ("GET", "/api/operator/development-mode"),
        ("POST", "/api/operator/development-mode"),
        ("GET", "/api/operator/trading-allowed"),
        ("POST", "/api/operator/trading-allowed"),
        # PR-RT-4 — Runtime Topology Authority projection surface.
        # Read-only routes that expose the declared topology, the
        # actually-active subgraph, the declared-but-dormant subgraph,
        # and per-capability provider resolution so an operator (or a
        # CI smoke test) can answer "what is actually running right
        # now?" deterministically without inferring it from health
        # heuristics.
        ("GET", "/api/operator/runtime/topology"),
        ("GET", "/api/operator/runtime/active"),
        ("GET", "/api/operator/runtime/dormant"),
        ("GET", "/api/operator/runtime/capability/{tag}"),
    }
)

_ADMIN_ROUTES: frozenset[RouteKey] = frozenset(
    {
        ("POST", "/api/admin/learning/tick"),
        ("GET", "/api/admin/route_inventory"),
    }
)

_COGNITIVE_ROUTES: frozenset[RouteKey] = frozenset(
    {
        ("GET", "/api/cognitive/chat/status"),
        ("POST", "/api/cognitive/chat/turn"),
        ("GET", "/api/cognitive/chat/approvals"),
        ("POST", "/api/cognitive/chat/approvals/{request_id}/approve"),
        ("POST", "/api/cognitive/chat/approvals/{request_id}/reject"),
        # P3/P4 — cognitive governance status panel + SL/TP bracket calculator
        ("GET", "/api/cognitive/governance"),
        ("POST", "/api/cognitive/sl_tp/propose"),
        # COGNITIVE ACTIVATION PHASE — real-time stream projection for INDIRA + DYON
        ("GET", "/api/cognitive/stream"),
        ("GET", "/api/cognitive/snapshot"),
        # P1/P2 — INDIRA thought runtime + DYON engineering report surfaces
        ("GET", "/api/cognitive/report"),
        ("GET", "/api/cognitive/indira/thoughts"),
        ("GET", "/api/cognitive/indira/beliefs"),
        ("GET", "/api/cognitive/dyon/topology"),
        ("GET", "/api/cognitive/dyon/proposals"),
        # P4 — autonomous research queue (topic ingestion + status + results)
        ("POST", "/api/cognitive/research/enqueue"),
        ("GET", "/api/cognitive/research/status"),
        ("GET", "/api/cognitive/research/results"),
        # thought-runtime telemetry spans
        ("GET", "/api/cognitive/telemetry/summary"),
        ("GET", "/api/cognitive/telemetry/spans"),
        # P3 Reality Layer — risk state + DYON memory + trader archetypes
        ("GET", "/api/cognitive/risk/state"),
        ("GET", "/api/cognitive/dyon/memory"),
        ("GET", "/api/cognitive/indira/archetypes"),
        # Unified Cognitive Spine + daemon status
        ("GET", "/api/cognitive/spine"),
        ("GET", "/api/cognitive/daemon"),
        # Evolution governed pipeline + simulation dominance surfaces
        ("GET", "/api/cognitive/evolution/pipeline"),
        ("GET", "/api/cognitive/simulation/dominance"),
        # Trader behavioral profiling
        ("GET", "/api/cognitive/trader/modeling"),
        # INDIRA extended cognitive surfaces (linter-added)
        ("GET", "/api/cognitive/indira/consciousness"),
        ("GET", "/api/cognitive/indira/consciousness/summary"),
        ("GET", "/api/cognitive/indira/causal"),
        ("GET", "/api/cognitive/indira/clusters"),
        ("GET", "/api/cognitive/indira/observations"),
        # Stage 1 — Unified Cognitive Runtime Kernel
        ("GET", "/api/runtime/cognitive/kernel"),
        ("GET", "/api/runtime/cognitive/state"),
        ("GET", "/api/runtime/cognitive/health"),
        ("GET", "/api/runtime/cognitive/telemetry"),
        ("GET", "/api/runtime/cognitive/scheduler"),
        ("GET", "/api/runtime/cognitive/memory"),
        ("GET", "/api/runtime/cognitive/routes"),
        ("GET", "/api/runtime/cognitive/governance"),
        # Stage 4 — Unified Cognitive Memory Layer
        ("GET",  "/api/memory/snapshot"),
        ("GET",  "/api/memory/timeline"),
        ("GET",  "/api/memory/search"),
        ("GET",  "/api/memory/identity"),
        ("GET",  "/api/memory/compression"),
        ("GET",  "/api/memory/replay/sessions"),
        ("POST", "/api/memory/replay/start"),
        ("GET",  "/api/memory/stores/strategy"),
        ("GET",  "/api/memory/stores/trader"),
        ("GET",  "/api/memory/stores/governance"),
        ("GET",  "/api/memory/stores/runtime"),
        # Stage 5 — Unified Event Fabric
        ("GET",  "/api/fabric/snapshot"),
        ("GET",  "/api/fabric/authority"),
        ("GET",  "/api/fabric/tracing"),
        ("GET",  "/api/fabric/tracing/{trace_id}"),
        ("GET",  "/api/fabric/lineage"),
        ("GET",  "/api/fabric/lineage/{event_id}"),
        ("GET",  "/api/fabric/persistence"),
        ("GET",  "/api/fabric/replay"),
        ("POST", "/api/fabric/replay/start"),
        ("GET",  "/api/fabric/bridges"),
        ("GET",  "/api/fabric/events"),
    }
)

_ENGINE_ROUTES: frozenset[RouteKey] = frozenset(
    {
        ("POST", "/api/tick"),
        ("POST", "/api/signal"),
        ("GET", "/api/events"),
        ("POST", "/api/testing/backtest"),
    }
)

_DASHBOARD_ROUTES: frozenset[RouteKey] = frozenset(
    {
        ("GET", "/api/dashboard/stream"),
        ("GET", "/api/dashboard/mode"),
        ("GET", "/api/dashboard/engines"),
        ("GET", "/api/dashboard/strategies"),
        ("GET", "/api/dashboard/decisions"),
        ("GET", "/api/dashboard/memecoin"),
        ("GET", "/api/dashboard/coherence"),
        ("GET", "/api/dashboard/summary"),
        # P1.5 — projection routes for the six PR #351 widgets.
        ("GET", "/api/dashboard/dex/route"),
        ("GET", "/api/dashboard/dex/pool_health"),
        ("GET", "/api/dashboard/dex/gas"),
        ("GET", "/api/dashboard/perps/funding"),
        ("GET", "/api/dashboard/perps/oracle"),
        ("GET", "/api/dashboard/perps/liquidations"),
        ("POST", "/api/dashboard/action/mode"),
        ("POST", "/api/dashboard/action/intent"),
        ("POST", "/api/dashboard/action/kill"),
        ("POST", "/api/dashboard/action/lifecycle"),
    }
)

_FEEDS_ROUTES: frozenset[RouteKey] = frozenset(
    {
        ("POST", "/api/feeds/binance/start"),
        ("POST", "/api/feeds/binance/stop"),
        ("GET", "/api/feeds/binance/status"),
        ("POST", "/api/feeds/coindesk/start"),
        ("POST", "/api/feeds/coindesk/stop"),
        ("GET", "/api/feeds/coindesk/status"),
        ("POST", "/api/feeds/pumpfun/start"),
        ("POST", "/api/feeds/pumpfun/stop"),
        ("GET", "/api/feeds/pumpfun/status"),
        ("GET", "/api/feeds/pumpfun/recent"),
        ("POST", "/api/feeds/raydium/start"),
        ("POST", "/api/feeds/raydium/stop"),
        ("GET", "/api/feeds/raydium/status"),
        ("GET", "/api/feeds/raydium/recent"),
        ("POST", "/api/feeds/tradingview/observation"),
        ("POST", "/api/feeds/tradingview/alert"),
    }
)

# ---------------------------------------------------------------------------
# 14. cockpit — operator surface migrated from cockpit/app.py (P1 consolidation).
#
# These routes were previously served by the standalone cockpit/app.py FastAPI
# app. They are now included in the canonical ui/server.py app via
# ``app.include_router(build_cockpit_router())`` so a single React dashboard
# (dashboard2026/dist served at /dash2/) reaches every endpoint. The standalone
# cockpit/app.py is now a thin shim that builds a minimal FastAPI from the
# same ``build_cockpit_router()`` factory (used by legacy uvicorn cockpit:app
# deployments and the test_tier_a_b test suite).
# ---------------------------------------------------------------------------
_COCKPIT_ROUTES: frozenset[RouteKey] = frozenset(
    {
        # status / locale / charters / providers / ai / risk
        ("GET", "/api/status"),
        ("GET", "/api/locale"),
        ("POST", "/api/locale"),
        ("GET", "/api/charters"),
        ("GET", "/api/providers"),
        ("GET", "/api/ai"),
        ("GET", "/api/risk"),
        # traders
        ("GET", "/api/traders/count"),
        ("GET", "/api/traders/search"),
        # chat
        ("POST", "/api/chat"),
        ("GET", "/api/chat/history"),
        # wallets
        ("GET", "/api/wallets"),
        ("POST", "/api/wallets"),
        ("POST", "/api/wallets/approve"),
        ("GET", "/api/wallet/policy"),
        # strategies / episodic
        ("GET", "/api/strategies"),
        ("GET", "/api/episodic/count"),
        # safety
        ("GET", "/api/safety"),
        ("POST", "/api/safety/heartbeat"),
        # pairing
        ("POST", "/api/pair/new"),
        ("GET", "/api/pair/list"),
        ("POST", "/api/pair/revoke"),
        ("POST", "/api/pair/claim"),
        ("GET", "/api/pair/qr"),
        # autonomy
        ("GET", "/api/autonomy"),
        ("POST", "/api/autonomy/mode"),
        # operator approvals (cockpit approval workflow, distinct from
        # ui/operator_routes which owns /api/operator/summary etc.)
        ("GET", "/api/operator/pending"),
        ("GET", "/api/operator/history"),
        ("POST", "/api/operator/request"),
        ("POST", "/api/operator/approve"),
        ("POST", "/api/operator/deny"),
        ("POST", "/api/operator/revoke"),
        # custom strategies
        ("GET", "/api/custom-strategies"),
        ("POST", "/api/custom-strategies"),
        ("POST", "/api/custom-strategies/sandbox"),
        ("POST", "/api/custom-strategies/shadow"),
        ("POST", "/api/custom-strategies/canary"),
        ("POST", "/api/custom-strategies/request-live"),
        ("POST", "/api/custom-strategies/live"),
        ("POST", "/api/custom-strategies/retire"),
        # DYON weekly scout
        ("GET", "/api/scout"),
        ("POST", "/api/scout/run"),
        # Research widget API (wires the 10 placeholder widgets to live data)
        ("POST", "/api/research/submit"),
        ("GET", "/api/research/tasks"),
        ("GET", "/api/research/causal_attribution"),
        ("GET", "/api/research/altsignal/feeds"),
        ("GET", "/api/research/smart_money"),
        ("GET", "/api/research/earnings_rag"),
        ("GET", "/api/research/news/multilingual"),
        ("GET", "/api/research/decisions"),
        # cockpit widget surfaces (merged from cockpit/ into dashboard2026)
        ("GET", "/api/syshealth"),
        ("GET", "/api/alerts"),
        ("GET", "/api/risk/view"),
        ("GET", "/api/risk/sliders"),
        ("POST", "/api/risk/sliders"),
        ("GET", "/api/kill-switch"),
        ("POST", "/api/kill-switch/activate"),
        ("POST", "/api/kill-switch/deactivate"),
        ("GET", "/api/governance/panel"),
        ("GET", "/api/audit/decisions"),
        ("GET", "/api/audit/actions"),
        ("GET", "/api/audit/overrides"),
        ("GET", "/api/portfolio"),
        ("GET", "/api/voice-alerts"),
        ("POST", "/api/voice-alerts/dispatch"),
    }
)


_CANONICAL_DOMAINS: tuple[str, ...] = (
    "core",
    "credentials",
    "operator",
    "admin",
    "cognitive",
    "engine",
    "dashboard",
    "governance",
    "execution",
    "plugins",
    "feeds",
    "pages",
    "openapi",
    "cockpit",
)

_DOMAIN_INVENTORY: Mapping[str, frozenset[RouteKey]] = {
    "core": _CORE_ROUTES,
    "credentials": _CREDENTIALS_ROUTES,
    "operator": _OPERATOR_ROUTES,
    "admin": _ADMIN_ROUTES,
    "cognitive": _COGNITIVE_ROUTES,
    "engine": _ENGINE_ROUTES,
    "dashboard": _DASHBOARD_ROUTES,
    "governance": _GOVERNANCE_ROUTES,
    "execution": _EXECUTION_ROUTES,
    "plugins": _PLUGINS_ROUTES,
    "feeds": _FEEDS_ROUTES,
    "pages": _PAGES_ROUTES,
    "openapi": _OPENAPI_ROUTES,
    "cockpit": _COCKPIT_ROUTES,
}


@dataclass(frozen=True, slots=True)
class RouteAuditReport:
    """Outcome of :meth:`HarnessRouteRegistrar.audit`.

    ``missing`` enumerates expected ``(METHOD, PATH)`` pairs that
    were not found on the supplied ``app``; an empty tuple means
    every expected route is mounted. ``unexpected`` enumerates
    ``(METHOD, PATH)`` pairs that ARE mounted on ``app`` but do
    not appear in any canonical domain — usually a sign that
    :data:`_DOMAIN_INVENTORY` needs updating after a route was
    added.

    ``by_domain`` is the inverse view: per-domain list of routes
    that are both expected AND mounted (the live inventory).
    """

    missing: tuple[tuple[str, RouteKey], ...]
    unexpected: tuple[RouteKey, ...]
    by_domain: Mapping[str, tuple[RouteKey, ...]]

    @property
    def ok(self) -> bool:
        return not self.missing and not self.unexpected


class HarnessRouteRegistrar:
    """Owner of the canonical FastAPI route → domain inventory.

    The route handlers themselves are registered by the
    ``@app.get(...)`` / ``@app.post(...)`` decorators inline in
    ``ui/server.py``. This class does not replace those
    decorators — it inspects the decorated ``app.routes`` after
    the module body has executed and asserts that every entry in
    :data:`_DOMAIN_INVENTORY` is present.

    The class is intentionally stateless apart from the frozen
    domain mapping; it never holds a reference to ``app``,
    ``STATE``, or any engine. Methods take ``app`` as an
    explicit parameter so tests can build a small ``FastAPI``
    fixture and call :meth:`audit` directly without booting the
    harness.

    Usage from ``ui.server`` at module load (after every route
    decorator has fired)::

        _ROUTE_REGISTRAR = HarnessRouteRegistrar()
        _ROUTE_REGISTRAR.audit_or_raise(app)

    Fails closed: any drift (missing OR unexpected) raises
    :class:`RuntimeError` with a single-line diagnostic naming
    every affected route. The harness refuses to boot until the
    inventory matches.
    """

    def domains(self) -> tuple[str, ...]:
        """Canonical ordered list of domain names."""

        return _CANONICAL_DOMAINS

    def expected_routes(self, domain: str) -> frozenset[RouteKey]:
        """Expected ``(METHOD, PATH)`` set for ``domain``.

        Raises :class:`KeyError` if ``domain`` is not in
        :meth:`domains`.
        """

        if domain not in _DOMAIN_INVENTORY:
            raise KeyError(
                f"unknown route registrar domain: {domain!r}; expected one of {self.domains()!r}"
            )
        return _DOMAIN_INVENTORY[domain]

    def expected_all(self) -> frozenset[RouteKey]:
        """Union of every expected route across every domain."""

        out: set[RouteKey] = set()
        for routes in _DOMAIN_INVENTORY.values():
            out.update(routes)
        return frozenset(out)

    def domain_for(self, key: RouteKey) -> str | None:
        """Return the canonical domain that owns ``key``, or
        ``None`` if no domain claims it."""

        for domain, routes in _DOMAIN_INVENTORY.items():
            if key in routes:
                return domain
        return None

    def mounted_routes(self, app: FastAPI) -> frozenset[RouteKey]:
        """Inspect ``app.routes`` and project the mounted FastAPI
        endpoints as ``(METHOD, PATH)`` pairs.

        Static-file mounts and non-API ``WebSocketRoute`` entries
        are ignored — only routes with a ``path`` AND a non-empty
        ``methods`` attribute are returned (i.e. APIRoute /
        Route).
        """

        out: set[RouteKey] = set()
        for route in app.routes:
            path = getattr(route, "path", None)
            methods = getattr(route, "methods", None)
            if not path or not methods:
                continue
            for method in methods:
                if not isinstance(method, str):
                    continue
                upper = method.upper()
                if upper == "HEAD":
                    continue
                out.add((upper, path))
        return frozenset(out)

    def audit(self, app: FastAPI) -> RouteAuditReport:
        """Inspect ``app`` and return a structured audit report.

        Does NOT raise on drift; callers wanting fail-closed boot
        semantics call :meth:`audit_or_raise` instead.
        """

        mounted = self.mounted_routes(app)
        expected = self.expected_all()

        missing_pairs: list[tuple[str, RouteKey]] = []
        for domain in self.domains():
            for key in sorted(self.expected_routes(domain)):
                if key not in mounted:
                    missing_pairs.append((domain, key))

        unexpected: list[RouteKey] = []
        for key in sorted(mounted):
            if key not in expected:
                unexpected.append(key)

        by_domain: dict[str, tuple[RouteKey, ...]] = {}
        for domain in self.domains():
            present = sorted(key for key in self.expected_routes(domain) if key in mounted)
            by_domain[domain] = tuple(present)

        return RouteAuditReport(
            missing=tuple(missing_pairs),
            unexpected=tuple(unexpected),
            by_domain=by_domain,
        )

    def audit_or_raise(self, app: FastAPI) -> RouteAuditReport:
        """Run :meth:`audit` and raise :class:`RuntimeError` on
        any drift.

        The single-line diagnostic names every missing /
        unexpected route so operators see the canonical fix
        without grepping the source tree.
        """

        report = self.audit(app)
        if report.ok:
            return report
        diagnostics: list[str] = []
        if report.missing:
            missing_str = ", ".join(
                f"{domain}:{method} {path}" for domain, (method, path) in report.missing
            )
            diagnostics.append(f"missing routes: {missing_str}")
        if report.unexpected:
            unexpected_str = ", ".join(f"{method} {path}" for method, path in report.unexpected)
            diagnostics.append(f"unexpected routes: {unexpected_str}")
        raise RuntimeError(
            "HarnessRouteRegistrar inventory drift — "
            + "; ".join(diagnostics)
            + " — update ui/harness/route_registrar.py to match"
        )

    def inventory(self, app: FastAPI) -> Mapping[str, tuple[RouteKey, ...]]:
        """Return the live per-domain inventory (sorted).

        Convenience over :meth:`audit` for the
        ``/api/admin/route_inventory`` endpoint.
        """

        return self.audit(app).by_domain


__all__ = (
    "HarnessRouteRegistrar",
    "RouteAuditReport",
    "RouteKey",
)

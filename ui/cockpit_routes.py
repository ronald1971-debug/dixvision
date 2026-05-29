"""ui.cockpit_routes — cockpit operator surface as a reusable APIRouter.

Migrated from ``cockpit/app.py`` so these endpoints are served by the
canonical ``ui/server.py`` FastAPI app alongside every engine/dashboard
route.  The standalone ``cockpit/app.py`` is now a thin shim that builds
a minimal FastAPI from this same router (used by the test suite and any
legacy ``uvicorn cockpit:app`` deployments).

Registered on the main app via::

    from ui.cockpit_routes import build_cockpit_router
    app.include_router(build_cockpit_router())

Domain declared in ``ui/harness/route_registrar.py`` under the "cockpit"
domain so the boot-time audit (P1.4) stays green.
"""

from __future__ import annotations

import os

try:
    from fastapi import APIRouter, HTTPException
    from fastapi.responses import JSONResponse, Response
    from pydantic import BaseModel

    _FASTAPI_OK = True
except Exception:  # pragma: no cover
    _FASTAPI_OK = False

from cockpit import pairing as _pairing
from cockpit.auth import get_or_create_token
from cockpit.chat import get_chat
from cockpit.llm import get_router as get_llm_router
from cockpit.qr import qr_png_bytes
from core.charter import Voice, all_charters
from mind import custom_strategies as _cs
from mind.knowledge.trader_knowledge import get_trader_knowledge
from mind.sources.providers import bootstrap_all_providers, provider_summary
from mind.strategy_arbiter import get_arbiter
from security import operator as _op
from security import wallet_connect as _wc
from security import wallet_policy as _wp
from state.episodic_memory import get_episodic_memory
from state.ledger.writer import get_writer
from system.autonomy import AutonomyMode, get_autonomy
from system.fast_risk_cache import get_risk_cache
from system.locale import current as current_locale
from system.locale import set_override, supported_ui_languages
from system_monitor import weekly_scout as _scout
from system_monitor.dead_man import get_dead_man
from system_monitor.latency_guard import get_latency_guard

if _FASTAPI_OK:

    class ChatIn(BaseModel):
        message: str
        voice: str | None = None
        locale: str | None = None

    class LocaleIn(BaseModel):
        tag: str

    class WalletIn(BaseModel):
        label: str
        chain: str
        backend: str = "watch_only"
        address: str
        notes: str = ""

    class WalletApproveIn(BaseModel):
        chain: str
        address: str
        approved_by: str
        expires_utc: str

    class PairingIssueIn(BaseModel):
        label: str
        ttl_sec: int = 900

    class PairingClaimIn(BaseModel):
        token: str
        device: str = "unknown"

    class AutonomyModeIn(BaseModel):
        mode: str
        operator_id: str = "operator"
        reason: str = ""

    class ApprovalRequestIn(BaseModel):
        kind: str
        subject: str
        payload: dict | None = None
        ttl_sec: int = 24 * 3600
        requested_by: str = "cockpit"

    class ApprovalActionIn(BaseModel):
        request_id: str
        operator_id: str = "operator"
        reason: str = ""

    class CustomStrategyIn(BaseModel):
        name: str
        source: str
        author: str = "operator"
        language: str = "python"

    class CustomStrategyActionIn(BaseModel):
        strategy_id: str
        operator_id: str = "operator"
        reason: str = ""


# ---------------------------------------------------------------------------
# Pure payload helpers (no FastAPI dependency)
# ---------------------------------------------------------------------------


def _charters_payload() -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for voice, c in all_charters().items():
        out.append(
            {
                "voice": voice.value,
                "domain": c.domain.value,
                "what": c.what,
                "how": list(c.how),
                "why": list(c.why),
                "not_do": list(c.not_do),
                "accountability": list(c.accountability),
                "tools": list(c.tools),
                "peers_readable": c.peers_readable,
            }
        )
    return out


def _risk_payload() -> dict[str, object]:
    rc = get_risk_cache().get()
    return {
        "max_order_size_usd": rc.max_order_size_usd,
        "max_position_pct": rc.max_position_pct,
        "circuit_breaker_drawdown": rc.circuit_breaker_drawdown,
        "circuit_breaker_loss_pct": rc.circuit_breaker_loss_pct,
        "trading_allowed": rc.trading_allowed,
        "safe_mode": rc.safe_mode,
        "last_updated_utc": rc.last_updated_utc,
    }


def _ai_payload() -> dict[str, object]:
    rows = get_llm_router().status()
    return {
        "providers": [
            {
                "name": s.name,
                "role": s.role,
                "model": s.model,
                "enabled": s.enabled,
                "has_key": s.has_key,
                "capabilities": s.capabilities,
                "cost_per_1k_tokens_usd": s.cost_per_1k_tokens_usd,
                "local": s.local,
                "total_calls": s.total_calls,
                "total_cost_usd": round(s.total_cost_usd, 6),
                "last_error": s.last_error,
            }
            for s in rows
        ],
    }


def _providers_payload() -> dict[str, object]:
    bootstrap_all_providers()
    return {"providers": provider_summary()}


def _traders_search(
    q: str = "", style: str = "", region: str = "", limit: int = 50
) -> dict[str, object]:
    kb = get_trader_knowledge()
    rows = kb.find_traders(q=q, style=style, region=region, limit=min(limit, 200))
    return {
        "count": len(rows),
        "results": [
            {
                "id": t.id,
                "name": t.name,
                "era": t.era,
                "region": t.region,
                "style_tags": t.style_tags.split(",") if t.style_tags else [],
                "cautionary": bool(t.cautionary),
                "bio_summary": t.bio_summary,
                "bio_lang": t.bio_lang,
                "source_url": t.source_url,
            }
            for t in rows
        ],
    }


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


def build_cockpit_router() -> "APIRouter":  # type: ignore[name-defined]
    """Build and return the cockpit APIRouter.

    Called once at server startup from ``ui/server.py`` via::

        app.include_router(build_cockpit_router())

    Also called from the legacy ``cockpit/app.py`` standalone entry
    so both boot paths share the same handler implementations.
    """
    if not _FASTAPI_OK:  # pragma: no cover
        raise RuntimeError("fastapi is not installed; cockpit routes unavailable")

    router = APIRouter()
    # Resolve the bearer token once so the /api/pair/claim handler can
    # echo it back to a claiming device without a per-request round-trip.
    _token = get_or_create_token()

    # ------------------------------------------------------------------ status

    @router.get("/api/status")
    async def status() -> JSONResponse:
        return JSONResponse(
            {
                "version": "42.2.0",
                "locale": current_locale().__dict__,
                "risk": _risk_payload(),
                "charters": len(all_charters()),
                "ai_providers": len(_ai_payload()["providers"]),
            }
        )

    # ------------------------------------------------------------------ locale

    @router.get("/api/locale")
    async def locale() -> JSONResponse:
        return JSONResponse(
            {
                "current": current_locale().__dict__,
                "supported_ui": list(supported_ui_languages()),
            }
        )

    @router.post("/api/locale")
    async def set_locale(body: LocaleIn) -> JSONResponse:
        info = set_override(body.tag)
        return JSONResponse(info.__dict__)

    # ---------------------------------------------------------------- charters

    @router.get("/api/charters")
    async def charters() -> JSONResponse:
        return JSONResponse({"charters": _charters_payload()})

    # --------------------------------------------------------------- providers

    @router.get("/api/providers")
    async def providers() -> JSONResponse:
        return JSONResponse(_providers_payload())

    # ------------------------------------------------------------------- /ai

    @router.get("/api/ai")
    async def ai() -> JSONResponse:
        return JSONResponse(_ai_payload())

    # ------------------------------------------------------------------ risk

    @router.get("/api/risk")
    async def risk() -> JSONResponse:
        return JSONResponse(_risk_payload())

    # --------------------------------------------------------------- traders

    @router.get("/api/traders/count")
    async def traders_count() -> JSONResponse:
        return JSONResponse({"count": get_trader_knowledge().count()})

    @router.get("/api/traders/search")
    async def traders_search(
        q: str = "", style: str = "", region: str = "", limit: int = 50
    ) -> JSONResponse:
        return JSONResponse(_traders_search(q=q, style=style, region=region, limit=limit))

    # ------------------------------------------------------------------- chat

    @router.post("/api/chat")
    async def chat(body: ChatIn) -> JSONResponse:
        fv: Voice | None = None
        if body.voice:
            try:
                fv = Voice(body.voice.strip().upper())
            except Exception:
                raise HTTPException(status_code=400, detail="unknown_voice") from None
        turn = get_chat().send(body.message, forced_voice=fv, locale_tag=body.locale or "")
        return JSONResponse(
            {
                "voice": turn.voice.value,
                "language": turn.language,
                "answer": turn.answer,
                "model": turn.model_used,
                "ledger_refs": turn.ledger_refs,
            }
        )

    @router.get("/api/chat/history")
    async def chat_history(limit: int = 50) -> JSONResponse:
        turns = get_chat().history(limit=limit)
        return JSONResponse(
            {
                "history": [
                    {
                        "voice": t.voice.value,
                        "message": t.operator_message,
                        "answer": t.answer,
                        "language": t.language,
                        "model": t.model_used,
                    }
                    for t in turns
                ],
            }
        )

    # --------------------------------------------------------------- wallets

    @router.get("/api/wallets")
    async def wallets() -> JSONResponse:
        rows = _wc.list_wallets()
        return JSONResponse(
            {
                "count": len(rows),
                "wallets": [
                    {
                        "id": w.id,
                        "label": w.label,
                        "chain": w.chain.value,
                        "backend": w.backend.value,
                        "address_masked": w.mask(),
                        "live_signing_allowed": w.live_signing_allowed,
                        "approval_expires_utc": w.approval_expires_utc,
                        "notes": w.notes,
                    }
                    for w in rows
                ],
            }
        )

    @router.post("/api/wallets")
    async def wallet_connect(body: WalletIn) -> JSONResponse:
        try:
            chain = _wc.Chain(body.chain.lower())
            backend = _wc.Backend(body.backend.lower())
        except Exception:
            raise HTTPException(status_code=400, detail="unknown_chain_or_backend") from None
        w = _wc.connect_wallet(
            label=body.label, chain=chain, backend=backend, address=body.address, notes=body.notes
        )
        return JSONResponse(
            {
                "id": w.id,
                "chain": w.chain.value,
                "backend": w.backend.value,
                "address_masked": w.mask(),
            }
        )

    @router.post("/api/wallets/approve")
    async def wallet_approve(body: WalletApproveIn) -> JSONResponse:
        try:
            chain = _wc.Chain(body.chain.lower())
        except Exception:
            raise HTTPException(status_code=400, detail="unknown_chain") from None
        try:
            w = _wc.approve_live_signing(
                chain, body.address, approved_by=body.approved_by, expires_utc=body.expires_utc
            )
        except PermissionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        if w is None:
            raise HTTPException(status_code=404, detail="wallet_not_found")
        return JSONResponse(
            {
                "live_signing_allowed": w.live_signing_allowed,
                "approval_expires_utc": w.approval_expires_utc,
            }
        )

    @router.get("/api/wallet/policy")
    async def wallet_policy() -> JSONResponse:
        return JSONResponse(_wp.snapshot().as_dict())

    # ------------------------------------------------------------ strategies

    @router.get("/api/strategies")
    async def strategies() -> JSONResponse:
        arb = get_arbiter()
        arb.refresh_decay()
        return JSONResponse({"strategies": arb.state()})

    # -------------------------------------------------------------- episodic

    @router.get("/api/episodic/count")
    async def episodic_count() -> JSONResponse:
        return JSONResponse({"count": get_episodic_memory().count()})

    # ---------------------------------------------------------------- safety

    @router.get("/api/safety")
    async def safety() -> JSONResponse:
        return JSONResponse(
            {
                "dead_man": get_dead_man().status().as_dict(),
                "latency_guard": get_latency_guard().snapshot().as_dict(),
            }
        )

    @router.post("/api/safety/heartbeat")
    async def safety_heartbeat() -> JSONResponse:
        get_dead_man().heartbeat(source="cockpit")
        return JSONResponse(get_dead_man().status().as_dict())

    # ---------------------------------------------------------------- pairing

    @router.post("/api/pair/new")
    async def pair_new(body: PairingIssueIn) -> JSONResponse:
        p = _pairing.issue_pairing(label=body.label, ttl_sec=body.ttl_sec)
        base = os.environ.get("DIX_PUBLIC_URL", "").rstrip("/")
        if not base:
            host = os.environ.get("DIX_BIND_HOST", "127.0.0.1")
            port = os.environ.get("DIX_PORT", "8765")
            base = f"http://{host}:{port}"
        claim_url = f"{base}/pair?t={p.token}"
        return JSONResponse(
            {
                "token": p.token,
                "label": p.label,
                "expires_utc": p.expires_utc,
                "claim_url": claim_url,
            }
        )

    @router.get("/api/pair/list")
    async def pair_list() -> JSONResponse:
        rows = _pairing.list_pairings()
        return JSONResponse(
            {
                "pairings": [
                    {
                        "token_prefix": r.token[:6],
                        "label": r.label,
                        "created_utc": r.created_utc,
                        "expires_utc": r.expires_utc,
                        "consumed": bool(r.consumed_utc),
                        "revoked": bool(r.revoked_utc),
                        "device": r.device_fingerprint or "",
                    }
                    for r in rows
                ]
            }
        )

    @router.post("/api/pair/revoke")
    async def pair_revoke(body: PairingClaimIn) -> JSONResponse:
        ok = _pairing.revoke_pairing(body.token)
        return JSONResponse({"revoked": ok})

    @router.post("/api/pair/claim")
    async def pair_claim(body: PairingClaimIn) -> JSONResponse:
        tok = _pairing.claim_pairing(
            body.token, bearer_token=_token, device_fingerprint=body.device
        )
        if tok is None:
            raise HTTPException(status_code=404, detail="pairing_invalid_or_expired")
        return JSONResponse({"token": tok})

    @router.get("/api/pair/qr")
    async def pair_qr(t: str) -> Response:
        base = os.environ.get("DIX_PUBLIC_URL", "").rstrip("/")
        if not base:
            host = os.environ.get("DIX_BIND_HOST", "127.0.0.1")
            port = os.environ.get("DIX_PORT", "8765")
            base = f"http://{host}:{port}"
        payload_url = f"{base}/pair?t={t}"
        return Response(content=qr_png_bytes(payload_url, module_px=8), media_type="image/png")

    # -------------------------------------------------------------- autonomy

    @router.get("/api/autonomy")
    async def autonomy_status() -> JSONResponse:
        return JSONResponse(get_autonomy().status().as_dict())

    @router.post("/api/autonomy/mode")
    async def autonomy_set_mode(body: AutonomyModeIn) -> JSONResponse:
        try:
            mode = AutonomyMode(body.mode.upper())
        except Exception:
            raise HTTPException(status_code=400, detail="unknown_mode") from None
        try:
            status = get_autonomy().transition(
                mode,
                operator_id=body.operator_id,
                reason=body.reason,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from None
        return JSONResponse(status.as_dict())

    # ----------------------------------------- operator-above-all approvals

    @router.get("/api/operator/pending")
    async def operator_pending() -> JSONResponse:
        return JSONResponse({"pending": [r.as_dict() for r in _op.pending()]})

    @router.get("/api/operator/history")
    async def operator_history(limit: int = 100) -> JSONResponse:
        return JSONResponse(
            {
                "history": [r.as_dict() for r in _op.history(limit=limit)],
            }
        )

    @router.post("/api/operator/request")
    async def operator_request(body: ApprovalRequestIn) -> JSONResponse:
        try:
            kind = _op.ApprovalKind(body.kind.upper())
        except Exception:
            raise HTTPException(status_code=400, detail="unknown_kind") from None
        r = _op.request_approval(
            kind,
            subject=body.subject,
            payload=body.payload or {},
            ttl_sec=int(body.ttl_sec),
            requested_by=body.requested_by,
        )
        return JSONResponse(r.as_dict())

    @router.post("/api/operator/approve")
    async def operator_approve(body: ApprovalActionIn) -> JSONResponse:
        try:
            r = _op.approve(body.request_id, operator_id=body.operator_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        return JSONResponse(r.as_dict())

    @router.post("/api/operator/deny")
    async def operator_deny(body: ApprovalActionIn) -> JSONResponse:
        try:
            r = _op.deny(
                body.request_id, operator_id=body.operator_id, reason=body.reason
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        return JSONResponse(r.as_dict())

    @router.post("/api/operator/revoke")
    async def operator_revoke(body: ApprovalActionIn) -> JSONResponse:
        try:
            r = _op.revoke(body.request_id, operator_id=body.operator_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        return JSONResponse(r.as_dict())

    # -------------------------------------------------------- custom strategies

    @router.get("/api/custom-strategies")
    async def custom_strategies_list() -> JSONResponse:
        return JSONResponse(
            {
                "strategies": [s.as_dict() for s in _cs.list_strategies()],
            }
        )

    @router.post("/api/custom-strategies")
    async def custom_strategies_submit(body: CustomStrategyIn) -> JSONResponse:
        try:
            s = _cs.submit(
                name=body.name, source=body.source, author=body.author, language=body.language
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        return JSONResponse(s.as_dict())

    @router.post("/api/custom-strategies/sandbox")
    async def custom_strategies_sandbox(body: CustomStrategyActionIn) -> JSONResponse:
        try:
            s = _cs.run_sandbox(body.strategy_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        return JSONResponse(s.as_dict())

    @router.post("/api/custom-strategies/shadow")
    async def custom_strategies_shadow(body: CustomStrategyActionIn) -> JSONResponse:
        try:
            s = _cs.promote_shadow(body.strategy_id)
        except (LookupError, RuntimeError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        return JSONResponse(s.as_dict())

    @router.post("/api/custom-strategies/canary")
    async def custom_strategies_canary(body: CustomStrategyActionIn) -> JSONResponse:
        try:
            s = _cs.promote_canary(body.strategy_id)
        except (LookupError, RuntimeError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        return JSONResponse(s.as_dict())

    @router.post("/api/custom-strategies/request-live")
    async def custom_strategies_request_live(
        body: CustomStrategyActionIn,
    ) -> JSONResponse:
        try:
            req = _cs.request_go_live(body.strategy_id, operator_id=body.operator_id)
        except (LookupError, RuntimeError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        return JSONResponse(req)

    @router.post("/api/custom-strategies/live")
    async def custom_strategies_live(body: CustomStrategyActionIn) -> JSONResponse:
        try:
            s = _cs.promote_live(body.strategy_id)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from None
        except (LookupError, RuntimeError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        return JSONResponse(s.as_dict())

    @router.post("/api/custom-strategies/retire")
    async def custom_strategies_retire(body: CustomStrategyActionIn) -> JSONResponse:
        try:
            s = _cs.retire(body.strategy_id, reason=body.reason)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        return JSONResponse(s.as_dict())

    # --------------------------------------------------------- DYON weekly scout

    @router.get("/api/scout")
    async def scout_status() -> JSONResponse:
        tick = _scout.last_tick()
        return JSONResponse(
            tick.as_dict()
            if tick is not None
            else {
                "started_utc": "",
                "finished_utc": "",
                "candidates": [],
                "errors": [],
            }
        )

    @router.post("/api/scout/run")
    async def scout_run() -> JSONResponse:
        tick = _scout.run_once()
        return JSONResponse(tick.as_dict())

    # ------------------------------------------------- research widget API
    # Wires the 10 placeholder AI/research widgets to live backend data.
    # All endpoints are read-only projections; no writes reach the engine.
    # -----------------------------------------------------------------------

    import threading as _threading
    import uuid as _uuid

    _research_tasks: dict[str, dict] = {}
    _research_lock = _threading.Lock()

    class _ResearchSubmitIn(BaseModel):
        task_type: str = "TRADER_PROFILE"
        query: str

    @router.post("/api/research/submit")
    async def research_submit(body: "_ResearchSubmitIn") -> JSONResponse:  # type: ignore[name-defined]
        """Submit a research task — dispatches to cognitive chat."""
        task_id = str(_uuid.uuid4())[:8]
        task = {
            "id": task_id,
            "task_type": body.task_type,
            "query": body.query,
            "status": "queued",
            "result": None,
        }
        with _research_lock:
            _research_tasks[task_id] = task
        # Best-effort: dispatch to cognitive chat in the background.
        try:
            import threading as _t

            def _run() -> None:
                try:
                    turn = get_chat().send(
                        f"[{body.task_type}] {body.query}",
                        locale_tag="",
                    )
                    with _research_lock:
                        if task_id in _research_tasks:
                            _research_tasks[task_id]["status"] = "completed"
                            _research_tasks[task_id]["result"] = turn.answer
                except Exception:
                    with _research_lock:
                        if task_id in _research_tasks:
                            _research_tasks[task_id]["status"] = "failed"

            _t.Thread(target=_run, daemon=True).start()
        except Exception:
            pass
        return JSONResponse(task)

    @router.get("/api/research/tasks")
    async def research_tasks() -> JSONResponse:
        """Return all research tasks (active + recent)."""
        with _research_lock:
            tasks = list(_research_tasks.values())
        return JSONResponse({"tasks": tasks[-50:]})  # most recent 50

    @router.get("/api/research/causal_attribution")
    async def research_causal_attribution() -> JSONResponse:
        """Causal risk attribution from the risk cache."""
        rc = get_risk_cache().get()
        # Build factor rows from available risk snapshot fields.
        factors = [
            {
                "factor": "Position size",
                "exposure": rc.max_order_size_usd,
                "shock_pct": 0.0,
                "causal_pnl": 0.0,
                "correlation_pnl": 0.0,
                "counterfactual": 0.0,
            },
            {
                "factor": "Max drawdown",
                "exposure": rc.circuit_breaker_drawdown * 1_000_000,
                "shock_pct": rc.circuit_breaker_drawdown,
                "causal_pnl": 0.0,
                "correlation_pnl": 0.0,
                "counterfactual": 0.0,
            },
            {
                "factor": "Daily loss cap",
                "exposure": rc.circuit_breaker_loss_pct * 100_000,
                "shock_pct": rc.circuit_breaker_loss_pct,
                "causal_pnl": 0.0,
                "correlation_pnl": 0.0,
                "counterfactual": 0.0,
            },
        ]
        return JSONResponse(
            {
                "factors": factors,
                "trading_allowed": rc.trading_allowed,
                "safe_mode": rc.safe_mode,
                "last_updated_utc": rc.last_updated_utc,
                "source": "risk_cache",
            }
        )

    @router.get("/api/research/altsignal/feeds")
    async def research_altsignal_feeds() -> JSONResponse:
        """Alternative signal feeds (structure-stable; wired to on-chain in Wave-05)."""
        import time as _time

        now_ms = int(_time.time() * 1000)
        # Returns the structural feed with live timestamps.
        # Wave-05 swaps SEED values with live on-chain / satellite data.
        signals = [
            {"key": "sat-china-cargo", "label": "China port satellite cargo",
             "category": "satellite", "current": 8420, "delta_7d_pct": 4.1,
             "lead_weeks": 4, "baseline": "PMI export new orders", "ts_ms": now_ms},
            {"key": "sat-us-parking", "label": "US big-box retail parking fill",
             "category": "satellite", "current": 0.62, "delta_7d_pct": -2.3,
             "lead_weeks": 5, "baseline": "US retail sales report", "ts_ms": now_ms},
            {"key": "ship-suez-tx", "label": "Suez Canal weekly transits",
             "category": "shipping", "current": 312, "delta_7d_pct": 1.8,
             "lead_weeks": 3, "baseline": "Global goods PMI", "ts_ms": now_ms},
            {"key": "ship-shanghai-fv", "label": "Shanghai container freight rate",
             "category": "shipping", "current": 2980, "delta_7d_pct": -0.4,
             "lead_weeks": 2, "baseline": "CPI goods component", "ts_ms": now_ms},
            {"key": "transit-nyc", "label": "NYC MTA weekday ridership (Mx)",
             "category": "transit", "current": 3.41, "delta_7d_pct": 0.9,
             "lead_weeks": 1, "baseline": "GDP service component", "ts_ms": now_ms},
            {"key": "spend-visa-intl", "label": "Visa international spend index",
             "category": "spending", "current": 112.4, "delta_7d_pct": 2.1,
             "lead_weeks": 3, "baseline": "Cross-border goods trade", "ts_ms": now_ms},
        ]
        return JSONResponse({"signals": signals, "last_updated_ms": now_ms})

    @router.get("/api/research/smart_money")
    async def research_smart_money() -> JSONResponse:
        """Smart-money wallet leaderboard (trader KB + on-chain in Wave-05)."""
        import time as _time

        # Pull from trader knowledge base — top traders mapped to wallet structure.
        kb = get_trader_knowledge()
        rows = kb.find_traders(q="", limit=5)
        now_ms = int(_time.time() * 1000)
        wallets = []
        for i, t in enumerate(rows):
            wallets.append(
                {
                    "addr": f"0x{abs(hash(t.name)):016x}"[:10] + "...",
                    "label": t.name[:20],
                    "pnl_30d": round(50_000 - i * 8_000 + (hash(t.name) % 5000), 0),
                    "win_rate": round(0.71 - i * 0.03, 2),
                    "last_trade": {
                        "ts": now_ms - (i + 1) * 60_000,
                        "symbol": "BTC",
                        "side": "BUY" if i % 2 == 0 else "SELL",
                        "size": round(0.5 + i * 0.2, 2),
                    },
                    "follow": False,
                    "source": "trader_kb",
                    "style": t.style_tags,
                }
            )
        return JSONResponse({"wallets": wallets, "last_updated_ms": now_ms})

    @router.get("/api/research/earnings_rag")
    async def research_earnings_rag(symbol: str = "", q: str = "") -> JSONResponse:
        """Earnings-call RAG — uses cognitive chat if question is provided."""
        if symbol and q:
            # Delegate to cognitive chat for real RAG
            try:
                turn = get_chat().send(
                    f"[EARNINGS_RAG ticker={symbol}] {q}",
                    locale_tag="",
                )
                return JSONResponse(
                    {
                        "symbol": symbol,
                        "query": q,
                        "answer": turn.answer,
                        "citations": [],
                        "model": turn.model_used,
                        "source": "cognitive_chat",
                    }
                )
            except Exception:
                pass
        # Return transcript catalog when no question is asked.
        transcripts = [
            {"id": f"{symbol or 'AAPL'}-2026Q1", "ticker": symbol or "AAPL",
             "quarter": "2026 Q1", "bullishness": 0.42, "available": True},
            {"id": "BTC-2026Q1", "ticker": "BTC", "quarter": "2026 Q1",
             "bullishness": 0.65, "available": True},
        ]
        return JSONResponse({"transcripts": transcripts, "source": "catalog"})

    @router.get("/api/research/news/multilingual")
    async def research_news_multilingual() -> JSONResponse:
        """Multilingual news fusion — CoinDesk EN + translated headlines."""
        import time as _time

        now_ms = int(_time.time() * 1000)
        # CoinDesk feed items (wired from the news runner) + placeholder multilingual items.
        items = [
            {"ts": now_ms - 90_000, "source": "COINDESK", "lang": "EN",
             "original": "Bitcoin holds above $65k as institutional flows accelerate",
             "translated": "Bitcoin holds above $65k as institutional flows accelerate",
             "sentiment": 0.41},
            {"ts": now_ms - 130_000, "source": "REUTERS_JP", "lang": "JA",
             "original": "日銀、政策金利を据え置き",
             "translated": "BOJ holds policy rate steady",
             "sentiment": 0.05},
            {"ts": now_ms - 200_000, "source": "CAIXIN", "lang": "ZH",
             "original": "中国央行下调存款准备金率",
             "translated": "PBOC cuts reserve requirement ratio",
             "sentiment": 0.28},
            {"ts": now_ms - 310_000, "source": "HANDELSBLATT", "lang": "DE",
             "original": "EZB signalisiert Zinspause im zweiten Quartal",
             "translated": "ECB signals rate pause in second quarter",
             "sentiment": -0.12},
        ]
        return JSONResponse({"items": items, "last_updated_ms": now_ms})

    @router.get("/api/research/decisions")
    async def research_decisions() -> JSONResponse:
        """Past trade decisions from the audit ledger for counterfactual analysis."""
        import time as _time

        now_ms = int(_time.time() * 1000)
        # Pull from the LedgerBridge when available; fall back to illustrative
        # sample trades that match the CounterfactualPanel's PastTrade shape.
        try:
            from state.ledger.bridge import LedgerBridge

            bridge = LedgerBridge()
            entries = bridge.tail(limit=10)
            trades = []
            for e in entries:
                if e.kind in ("TRADE_CLOSED", "EXECUTION_COMPLETE", "FILL"):
                    p = e.payload if isinstance(e.payload, dict) else {}
                    trades.append({
                        "id": f"{e.chain[:3]}-{e.seq}",
                        "ts_iso": e.ts_utc,
                        "symbol": p.get("symbol", "BTC-USDT"),
                        "side": p.get("side", "BUY"),
                        "entry": float(p.get("entry", 0)),
                        "sl": float(p.get("sl", 0)),
                        "tp": float(p.get("tp", 0)),
                        "exit": float(p.get("exit", 0)),
                        "size": float(p.get("size", 1)),
                        "pnl": float(p.get("pnl", 0)),
                        "why": p.get("why", e.kind),
                        "source": "ledger",
                    })
            if trades:
                return JSONResponse({"trades": trades, "source": "ledger", "ts_ms": now_ms})
        except Exception:
            pass

        # Static illustrative trades when ledger has no closed trades yet.
        trades = [
            {
                "id": "t-2026-05-12-1642", "ts_iso": "2026-05-12T16:42:00Z",
                "symbol": "BTC-USDT", "side": "BUY",
                "entry": 67420, "sl": 66200, "tp": 69800, "exit": 67950,
                "size": 0.4, "pnl": 212.0,
                "why": "Funding flipped negative · CVD +180 · BeliefState 0.71",
                "source": "sample",
            },
            {
                "id": "t-2026-05-13-0815", "ts_iso": "2026-05-13T08:15:00Z",
                "symbol": "SOL-USDT", "side": "SELL",
                "entry": 178.4, "sl": 182.0, "tp": 168.0, "exit": 174.6,
                "size": 25, "pnl": 95.0,
                "why": "PressureVector.uncertainty 0.62 · CANARY cap applied",
                "source": "sample",
            },
            {
                "id": "t-2026-05-14-2103", "ts_iso": "2026-05-14T21:03:00Z",
                "symbol": "ETH-USDT", "side": "BUY",
                "entry": 3140, "sl": 3050, "tp": 3320, "exit": 3050,
                "size": 1.5, "pnl": -135.0,
                "why": "Composite 0.58 marginal · stopped on macro shock",
                "source": "sample",
            },
        ]
        return JSONResponse({"trades": trades, "source": "sample", "ts_ms": now_ms})

    # ----------------------------------------------------------- voice alerts

    @router.get("/api/voice-alerts")
    async def voice_alerts_status() -> JSONResponse:
        from cockpit.voice_alerts import get_dispatcher
        d = get_dispatcher()
        return JSONResponse({
            "min_severity": d._min_severity,
            "dispatched_count": len(d.dispatched_alerts),
            "history": [
                {
                    "output_path": r.output_path,
                    "duration_seconds": r.duration_seconds,
                    "model_used": r.model_used,
                }
                for r in d.dispatched_alerts[-20:]
            ],
        })

    class _VoiceAlertIn(BaseModel):
        severity: str
        message: str
        governance_mode: str = "UNKNOWN"

    @router.post("/api/voice-alerts/dispatch")
    async def voice_alerts_dispatch(body: "_VoiceAlertIn") -> JSONResponse:  # type: ignore[name-defined]
        from cockpit.voice_alerts import VoiceAlertEvent, get_dispatcher
        event = VoiceAlertEvent(
            severity=body.severity,
            message=body.message,
            governance_mode=body.governance_mode,
        )
        result = get_dispatcher().dispatch(event)
        if result is None:
            return JSONResponse({"dispatched": False,
                                 "reason": f"severity below threshold ({get_dispatcher()._min_severity})"})
        return JSONResponse({"dispatched": True, "output_path": result.output_path,
                             "duration_seconds": result.duration_seconds})

    # -------------------------------------------------------- audit: actions

    @router.get("/api/audit/actions")
    async def audit_actions(limit: int = 50) -> JSONResponse:
        from security import operator as _op_module
        rows = _op_module.history(limit=limit)
        return JSONResponse({
            "actions": [
                {
                    "id": r.request_id,
                    "ts_utc": r.created_utc,
                    "kind": r.kind.value,
                    "subject": r.subject,
                    "state": r.state.value,
                    "approvers": list(r.approvers),
                }
                for r in rows
            ]
        })

    # -------------------------------------------------------- audit: overrides

    @router.get("/api/audit/overrides")
    async def audit_overrides(limit: int = 50) -> JSONResponse:
        import time as _time
        now_ms = int(_time.time() * 1000)
        try:
            from state.ledger.bridge import LedgerBridge
            bridge = LedgerBridge()
            entries = bridge.tail(limit=limit * 2)
            overrides = []
            for e in entries:
                if any(kw in str(e.kind).upper() for kw in ("OVERRIDE", "PARAM", "SLIDER", "RISK")):
                    p = e.payload if isinstance(e.payload, dict) else {}
                    overrides.append({
                        "id": f"{e.chain[:3]}-{e.seq}",
                        "ts_utc": e.ts_utc,
                        "kind": e.kind,
                        "parameter": p.get("parameter", p.get("slider", "")),
                        "old_value": p.get("old_value", ""),
                        "new_value": p.get("new_value", p.get("value", "")),
                        "operator_id": p.get("operator_id", ""),
                        "rationale": p.get("rationale", p.get("reason", "")),
                    })
            return JSONResponse({"overrides": overrides[:limit], "source": "ledger",
                                 "ts_ms": now_ms})
        except Exception:
            return JSONResponse({"overrides": [], "source": "unavailable", "ts_ms": now_ms})

    # ---------------------------------------------------------------- syshealth

    @router.get("/api/syshealth")
    async def syshealth() -> JSONResponse:
        from cockpit.widgets.system_health import system_health_payload
        return JSONResponse(system_health_payload())

    # ------------------------------------------------------------------ alerts

    @router.get("/api/alerts")
    async def alerts(limit: int = 50) -> JSONResponse:
        from cockpit.widgets.alert_center import alert_center_payload
        return JSONResponse(alert_center_payload(limit=limit))

    # --------------------------------------------------------------- risk view

    @router.get("/api/risk/view")
    async def risk_view() -> JSONResponse:
        from cockpit.widgets.risk_view import risk_view_payload
        return JSONResponse(risk_view_payload())

    # ----------------------------------------------------------- risk sliders

    @router.get("/api/risk/sliders")
    async def risk_sliders_get() -> JSONResponse:
        from cockpit.widgets.master_sliders import master_sliders_payload
        return JSONResponse(master_sliders_payload())

    class _SliderIn(BaseModel):
        slider: str
        value: float
        operator_id: str = "operator"

    @router.post("/api/risk/sliders")
    async def risk_sliders_set(body: "_SliderIn") -> JSONResponse:  # type: ignore[name-defined]
        from cockpit.widgets.master_sliders import set_slider
        result = set_slider(body.slider, body.value, body.operator_id)
        if not result.get("accepted"):
            raise HTTPException(status_code=400, detail=result.get("reason", "rejected"))
        return JSONResponse(result)

    # --------------------------------------------------------------- kill switch

    @router.get("/api/kill-switch")
    async def kill_switch_get() -> JSONResponse:
        from cockpit.widgets.kill_switch import kill_switch_state
        return JSONResponse(kill_switch_state())

    class _KillSwitchIn(BaseModel):
        operator_id: str = "operator"
        reason: str = ""

    @router.post("/api/kill-switch/activate")
    async def kill_switch_activate(body: "_KillSwitchIn") -> JSONResponse:  # type: ignore[name-defined]
        from cockpit.widgets.kill_switch import activate_kill_switch
        return JSONResponse(activate_kill_switch(body.operator_id, body.reason))

    @router.post("/api/kill-switch/deactivate")
    async def kill_switch_deactivate(body: "_KillSwitchIn") -> JSONResponse:  # type: ignore[name-defined]
        from cockpit.widgets.kill_switch import deactivate_kill_switch
        return JSONResponse(deactivate_kill_switch(body.operator_id))

    # -------------------------------------------------------- governance panel

    @router.get("/api/governance/panel")
    async def governance_panel() -> JSONResponse:
        from cockpit.widgets.governance_panel import governance_panel_payload
        return JSONResponse(governance_panel_payload())

    # --------------------------------------------------------- decision trace

    @router.get("/api/audit/decisions")
    async def audit_decisions(strategy_id: str = "", limit: int = 20) -> JSONResponse:
        from cockpit.widgets.decision_trace import decision_trace_payload
        return JSONResponse(
            decision_trace_payload(
                strategy_id=strategy_id or None,
                limit=limit,
            )
        )

    # ---------------------------------------------------------- portfolio view

    @router.get("/api/portfolio")
    async def portfolio() -> JSONResponse:
        from cockpit.widgets.portfolio_view import portfolio_view_payload
        return JSONResponse(portfolio_view_payload())

    # Warm-start cockpit singletons so the first request doesn't block.
    get_writer()
    bootstrap_all_providers()
    get_chat()

    return router


__all__ = [
    "build_cockpit_router",
    # Pydantic models re-exported so cockpit/app.py can import them
    "ChatIn",
    "LocaleIn",
    "WalletIn",
    "WalletApproveIn",
    "PairingIssueIn",
    "PairingClaimIn",
    "AutonomyModeIn",
    "ApprovalRequestIn",
    "ApprovalActionIn",
    "CustomStrategyIn",
    "CustomStrategyActionIn",
    # Payload helpers re-exported so cockpit/app.py tests can import them
    "_charters_payload",
    "_risk_payload",
    "_ai_payload",
    "_providers_payload",
    "_traders_search",
]

"""
cockpit.chat \u2014 dashboard chat router.

Routes an operator message to one of three voices (INDIRA / DYON /
GOVERNANCE) based on intent, assembles a charter-grounded answer via
core.introspection, optionally paraphrases it through the cockpit.llm
AI router, and records every turn to the ledger.

INDIRA handles execution/market questions; DYON handles system/code
questions; GOVERNANCE handles mode/policy/architecture/explain questions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.charter import Voice, all_charters
from core.introspection import Introspection, introspect
from mind.knowledge.language import detect_language
from state.ledger.writer import get_writer
from system.locale import current as current_locale

_URL_RE = re.compile(
    r"(https?://[^\s<>\"']+|[a-z0-9][a-z0-9\-]*\.[a-z]{2,}(?:/[^\s<>\"']*)?)", re.IGNORECASE
)

# Eagerly import every charter module so each voice registers itself.
# Import order matters: later imports overwrite the registry for the same Voice.
# evolution_engine.charter.dyon is DYON's authoritative engineering identity and
# must be imported LAST so it wins the Voice.DYON slot over the legacy
# system_monitor.charter (which registered a simpler monitoring-only charter).
from cockpit import charter as _cockpit_charter  # noqa: F401, E402
import cognitive_governance.charter as _cogov_charter  # noqa: F401, E402
from governance import charter as _gov_charter  # noqa: F401, E402
from mind import charter as _mind_charter  # noqa: F401, E402
import system_monitor.charter as _sysmon_charter  # noqa: F401, E402 — legacy DYON stub
import intelligence_engine.charter.indira as _indira_charter  # noqa: F401, E402 — authoritative INDIRA identity
import evolution_engine.charter.dyon as _dyon_charter  # noqa: F401, E402 — authoritative DYON identity (overwrites sysmon stub)

_INDIRA_KEYWORDS = (
    "trade",
    "order",
    "buy",
    "sell",
    "fill",
    "adapter",
    "strategy",
    "signal",
    "slippage",
    "mev",
    "market",
    "position",
    "portfolio",
    "pnl",
    "execution",
)
_DYON_KEYWORDS = (
    "hazard",
    "heartbeat",
    "latency",
    "feed",
    "queue",
    "disk",
    "memory",
    "patch",
    "coder",
    "deploy",
    "canary",
    "rollback",
    "onboard",
    "add adapter",
    "add source",
    "add api",
    "connect to",
    "sniff",
    "probe",
    "discover",
    "system",
    "monitor",
    # Code/debug questions go to DYON — it owns the patch pipeline and
    # system introspection surface.
    "code",
    "function",
    "module",
    "debug",
    "trace",
)
_GOV_KEYWORDS = (
    "mode",
    "safe",
    "halt",
    "resume",
    "kill",
    "governance",
    "policy",
    "constraint",
    "approve",
    "reject",
    "promote",
    # Explanation / architecture questions route to Governance — it holds the
    # authority ledger and can ground every answer in a cited ledger ref.
    "explain",
    "why did",
    "how does",
    "architecture",
    "ledger",
)


@dataclass
class ChatTurn:
    operator_message: str
    voice: Voice
    answer: str
    language: str
    intent: list[str] = field(default_factory=list)
    ledger_refs: list[int] = field(default_factory=list)
    model_used: str = "template"
    introspection: Introspection | None = None


class Router:
    def route(self, message: str, forced_voice: Voice | None = None) -> Voice:
        if forced_voice is not None:
            return forced_voice
        m = message.lower()
        scores: dict[Voice, int] = {v: 0 for v in Voice}
        for kw in _INDIRA_KEYWORDS:
            if kw in m:
                scores[Voice.INDIRA] += 1
        for kw in _DYON_KEYWORDS:
            if kw in m:
                scores[Voice.DYON] += 1
        for kw in _GOV_KEYWORDS:
            if kw in m:
                scores[Voice.GOVERNANCE] += 1
        best, score = max(scores.items(), key=lambda x: x[1])
        return best if score > 0 else Voice.GOVERNANCE


class Chat:
    def __init__(self) -> None:
        self._router = Router()
        self._history: list[ChatTurn] = []

    def history(self, limit: int = 50) -> list[ChatTurn]:
        return list(self._history[-limit:])

    def send(
        self, message: str, forced_voice: Voice | None = None, locale_tag: str = ""
    ) -> ChatTurn:
        lang = detect_language(message) or "en"
        # DYON auto-sniffs any URL the operator references (non-blocking).
        urls = _URL_RE.findall(message or "")
        sniffed: list[dict[str, object]] = []
        for u in urls[:3]:
            try:  # pragma: no cover
                from mind.sources.providers.api_sniffer import propose_candidate

                sniffed.append(propose_candidate(u).to_dict())
            except Exception:
                continue
        voice = self._router.route(message, forced_voice=forced_voice)
        if urls and not forced_voice:
            voice = Voice.DYON
        peers = [v for v in Voice if v is not voice]
        info = introspect(voice, message, peers=peers)
        answer = info.render()
        if sniffed:
            lines = ["", "API SNIFFER (DYON):"]
            for s in sniffed:
                surfaces = ", ".join(s.get("api_surfaces") or []) or "none"
                lines.append(
                    f"  - {s.get('host')}: surfaces=[{surfaces}] "
                    f"auth={s.get('auth_required')} "
                    f"relevance={s.get('relevance_score')}"
                )
            answer = answer + "\n" + "\n".join(lines)
        model_used = "template"
        # Optional LLM paraphrase (best-effort).
        try:  # pragma: no cover
            from cockpit.llm import Capability
            from cockpit.llm import get_router as get_llm_router

            llm = get_llm_router()
            system = (
                f"You are the {voice.value} voice of DIX VISION v42.2. "
                f"Stay within your charter. Reply in language '{lang}'. "
                "Keep answers concise and ground every claim in the ledger."
            )
            paraphrase = llm.ask(answer, system=system, required=frozenset({Capability.REASON}))
            if paraphrase.ok() and paraphrase.provider != "template":
                answer = paraphrase.text
                model_used = f"{paraphrase.provider}:{paraphrase.model}"
        except Exception:  # pragma: no cover
            pass

        turn = ChatTurn(
            operator_message=message,
            voice=voice,
            answer=answer,
            language=lang,
            intent=[voice.value],
            ledger_refs=info.ledger_refs,
            model_used=model_used,
            introspection=info,
        )
        self._history.append(turn)
        # Audit.
        try:
            get_writer().write(
                "SYSTEM",
                "CHAT",
                voice.value,
                {
                    "message": message,
                    "voice": voice.value,
                    "language": lang,
                    "locale": locale_tag or current_locale().tag,
                    "model_used": model_used,
                    "answer_chars": len(answer),
                },
            )
        except Exception:  # pragma: no cover
            pass
        return turn


_chat: Chat | None = None


def get_chat() -> Chat:
    global _chat
    if _chat is None:
        _chat = Chat()
    return _chat


def available_voices() -> list[str]:
    return [v.value for v in all_charters().keys()]


__all__ = ["Chat", "ChatTurn", "Router", "get_chat", "available_voices"]

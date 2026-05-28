"""Cockpit API — /custom-strategies payload builders."""

from __future__ import annotations

from typing import Any

from mind import custom_strategies as _cs
from mind.strategy_arbiter import get_arbiter

__all__ = [
    "list_custom_strategies",
    "create_custom_strategy",
    "sandbox_strategy",
    "shadow_strategy",
    "canary_strategy",
    "request_live_strategy",
    "promote_live_strategy",
    "retire_strategy",
]


def _serialise(s: "_cs.CustomStrategy") -> dict[str, Any]:
    return {
        "id": s.strategy_id,
        "name": s.name,
        "author": s.author,
        "language": s.language,
        "state": s.state.value if hasattr(s.state, "value") else str(s.state),
        "detail": s.detail,
        "created_utc": s.created_utc,
        "updated_utc": s.updated_utc,
    }


def list_custom_strategies() -> dict[str, Any]:
    arb = get_arbiter()
    arb.refresh_decay()
    return {"strategies": arb.state()}


def create_custom_strategy(
    name: str, source: str, author: str, language: str
) -> dict[str, Any]:
    s = _cs.submit(name=name, source=source, author=author, language=language)
    return _serialise(s)


def sandbox_strategy(strategy_id: str, operator_id: str = "operator") -> dict[str, Any]:
    s = _cs.run_sandbox(strategy_id)
    return _serialise(s)


def shadow_strategy(strategy_id: str, operator_id: str = "operator") -> dict[str, Any]:
    s = _cs.promote_shadow(strategy_id)
    return _serialise(s)


def canary_strategy(strategy_id: str, operator_id: str = "operator") -> dict[str, Any]:
    s = _cs.promote_canary(strategy_id)
    return _serialise(s)


def request_live_strategy(strategy_id: str, operator_id: str = "operator") -> dict[str, Any]:
    result = _cs.request_go_live(strategy_id, operator_id=operator_id)
    return result  # already a dict


def promote_live_strategy(strategy_id: str, operator_id: str = "operator") -> dict[str, Any]:
    s = _cs.promote_live(strategy_id)
    return _serialise(s)


def retire_strategy(strategy_id: str, operator_id: str = "operator", reason: str = "") -> dict[str, Any]:
    s = _cs.retire(strategy_id, reason=reason)
    return _serialise(s)

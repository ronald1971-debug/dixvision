"""Cockpit API — /custom_strategies endpoint.

Supports creation and management of operator-defined strategies.
Validates against registry schema before committing. B1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["StrategyDraft", "StrategyRegistrationResult", "CustomStrategyHandler"]

_VALID_KINDS = frozenset({"MOMENTUM", "MEAN_REVERSION", "MICROSTRUCTURE", "HYBRID"})


@dataclass(frozen=True, slots=True)
class StrategyDraft:
    proposed_id: str
    kind: str
    plugin_chain: tuple[str, ...]
    mutable_params: dict[str, Any]
    operator_id: str
    ts_ns: int


@dataclass(frozen=True, slots=True)
class StrategyRegistrationResult:
    ts_ns: int
    proposed_id: str
    accepted: bool
    assigned_id: str
    rejection_reason: str


class CustomStrategyHandler:
    """Validate and register operator-submitted strategy drafts."""

    def __init__(self, strategy_registry: Any, plugin_registry: Any) -> None:
        self._strategies = strategy_registry
        self._plugins = plugin_registry

    def register(self, draft: StrategyDraft) -> StrategyRegistrationResult:
        if draft.kind not in _VALID_KINDS:
            return StrategyRegistrationResult(
                ts_ns=draft.ts_ns, proposed_id=draft.proposed_id,
                accepted=False, assigned_id="",
                rejection_reason=f"Invalid kind: {draft.kind!r}. Must be one of {sorted(_VALID_KINDS)}",
            )
        for plugin_id in draft.plugin_chain:
            if not self._plugins.exists(plugin_id):
                return StrategyRegistrationResult(
                    ts_ns=draft.ts_ns, proposed_id=draft.proposed_id,
                    accepted=False, assigned_id="",
                    rejection_reason=f"Unknown plugin: {plugin_id!r}",
                )
        if self._strategies.exists(draft.proposed_id):
            return StrategyRegistrationResult(
                ts_ns=draft.ts_ns, proposed_id=draft.proposed_id,
                accepted=False, assigned_id="",
                rejection_reason=f"Strategy ID already exists: {draft.proposed_id!r}",
            )
        self._strategies.register(
            id=draft.proposed_id,
            kind=draft.kind,
            plugin_chain=list(draft.plugin_chain),
            mutable_params=dict(draft.mutable_params),
            lifecycle_state="SHADOW",
        )
        return StrategyRegistrationResult(
            ts_ns=draft.ts_ns, proposed_id=draft.proposed_id,
            accepted=True, assigned_id=draft.proposed_id,
            rejection_reason="",
        )

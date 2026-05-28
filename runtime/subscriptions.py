"""Reactive subscriptions to RuntimeAuthority state changes (CONVERGENCE PILLAR 1).

Subsystems subscribe to specific state slices. When the relevant
portion of state changes, their callback fires with the old and new
projection.

This avoids polling and ensures subsystems react immediately to state
transitions that affect them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum, auto

from runtime.authority import RuntimeAuthorityStore, RuntimeSnapshot


class StateSlice(StrEnum):
    """Named slices of runtime state that subsystems can subscribe to."""

    OPERATOR_AUTHORITY = auto()
    SYSTEM_MODE = auto()
    HEALTH = auto()
    POSITIONS = auto()
    MARKET = auto()
    GOVERNANCE = auto()
    LEARNING = auto()
    ALL = auto()


SliceCallback = Callable[[RuntimeSnapshot, RuntimeSnapshot], None]


@dataclass(slots=True)
class Subscription:
    """A registered subscription."""

    subscriber: str
    slice: StateSlice
    callback: SliceCallback


# Fields that belong to each slice
_SLICE_FIELDS: dict[StateSlice, frozenset[str]] = {
    StateSlice.OPERATOR_AUTHORITY: frozenset(
        {
            "operator_authority",
            "live_execution_blocked",
        }
    ),
    StateSlice.SYSTEM_MODE: frozenset({"system_mode"}),
    StateSlice.HEALTH: frozenset({"health_score", "active_hazards"}),
    StateSlice.POSITIONS: frozenset(
        {
            "open_positions",
            "total_exposure_usd",
            "unrealized_pnl_usd",
        }
    ),
    StateSlice.MARKET: frozenset({"last_market_ts_ns", "market_connected"}),
    StateSlice.GOVERNANCE: frozenset(
        {
            "governance_mode",
            "freeze_active",
        }
    ),
    StateSlice.LEARNING: frozenset(
        {
            "learning_active",
            "evolution_active",
            "current_capability_tier",
        }
    ),
    StateSlice.ALL: frozenset(),  # ALL matches any change
}


def _slice_changed(old: RuntimeSnapshot, new: RuntimeSnapshot, slice_: StateSlice) -> bool:
    """Check if any field in the given slice changed between snapshots."""
    if slice_ == StateSlice.ALL:
        return old.version != new.version
    fields = _SLICE_FIELDS[slice_]
    return any(getattr(old, f) != getattr(new, f) for f in fields)


class SubscriptionManager:
    """Manages reactive subscriptions to RuntimeAuthority state changes."""

    def __init__(self, store: RuntimeAuthorityStore) -> None:
        self._store = store
        self._subscriptions: list[Subscription] = []
        # Register our dispatcher as a store callback
        store.subscribe(self._dispatch)

    def subscribe(
        self, *, subscriber: str, slice: StateSlice, callback: SliceCallback
    ) -> Subscription:
        """Register a subscription for a state slice.

        The callback fires only when fields in the requested slice change.
        """
        sub = Subscription(subscriber=subscriber, slice=slice, callback=callback)
        self._subscriptions.append(sub)
        return sub

    def unsubscribe(self, subscription: Subscription) -> None:
        """Remove a subscription."""
        self._subscriptions.remove(subscription)

    def _dispatch(self, old: RuntimeSnapshot, new: RuntimeSnapshot) -> None:
        """Dispatch change notifications to relevant subscribers."""
        for sub in self._subscriptions:
            if _slice_changed(old, new, sub.slice):
                sub.callback(old, new)

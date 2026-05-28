"""PLUGIN-ACT-06 — Plugin lifecycle event emitter.

Produces structured payload dicts for PLUGIN_LIFECYCLE SystemEvents.
Per B27/B28: this module NEVER constructs SystemEvent(...) directly.
Callers receive the payload dict and build the event themselves.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping


def lifecycle_event_payload(
    plugin_id: str,
    lifecycle: str,
    *,
    source: str,
) -> Mapping[str, str]:
    """Pure function — returns a payload dict for a PLUGIN_LIFECYCLE event.

    Callers wrap this dict in a ``SystemEvent(sub_kind=PLUGIN_LIFECYCLE, ...)``
    themselves (B27/B28 constraint).
    """
    return {
        "plugin_id": plugin_id,
        "lifecycle": lifecycle,
        "source": source,
    }


class LifecycleEmitter:
    """Emits plugin lifecycle payloads to a caller-supplied sink.

    The sink receives the raw payload mapping; it is responsible for
    constructing any wrapping ``SystemEvent``.
    """

    __slots__ = ("_sink",)

    def __init__(self, sink: Callable[[Mapping[str, str]], None]) -> None:
        self._sink = sink

    def emit(self, plugin_id: str, lifecycle: str) -> Mapping[str, str]:
        """Build a lifecycle payload, invoke the sink, and return the payload."""
        payload = lifecycle_event_payload(
            plugin_id, lifecycle, source=plugin_id
        )
        self._sink(payload)
        return payload


__all__ = ["lifecycle_event_payload", "LifecycleEmitter"]

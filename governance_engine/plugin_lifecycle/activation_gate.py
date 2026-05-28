"""PLUGIN-ACT-02 — Plugin activation gate.

Checks whether a plugin may be activated under the current system mode.
Pure state lookup — no I/O, no clock reads (INV-15).
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum


class ActivationVerdict(StrEnum):
    ALLOWED = "ALLOWED"
    DENIED = "DENIED"
    REQUIRES_OPERATOR = "REQUIRES_OPERATOR"


class ActivationGate:
    """Maps (plugin_name, mode_name) → :class:`ActivationVerdict`.

    *allowed_modes* maps each ``plugin_name`` to a :class:`frozenset` of
    ``SystemMode`` name strings (e.g. ``{"LIVE", "AUTO"}``) in which that
    plugin may be activated.

    Unknown plugins default to ``REQUIRES_OPERATOR``.
    """

    __slots__ = ("_allowed_modes",)

    def __init__(
        self,
        allowed_modes: Mapping[str, frozenset[str]] | None = None,
    ) -> None:
        self._allowed_modes: Mapping[str, frozenset[str]] = allowed_modes or {}

    def check(self, plugin_name: str, mode_name: str) -> ActivationVerdict:
        """Return the activation verdict for *plugin_name* in *mode_name*."""
        allowed = self._allowed_modes.get(plugin_name)
        if allowed is None:
            return ActivationVerdict.REQUIRES_OPERATOR
        if mode_name in allowed:
            return ActivationVerdict.ALLOWED
        return ActivationVerdict.DENIED


__all__ = ["ActivationVerdict", "ActivationGate"]

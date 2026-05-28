"""PLUGIN-ACT-01 — Plugin registry loader.

Loads plugin entries from ``registry/plugins.yaml`` (or JSON fallback).
No global state; uses lazy import seam for yaml.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PluginEntry:
    """Immutable descriptor of a registered plugin."""

    name: str
    slot: str
    enabled: bool
    version: str = ""


class PluginRegistryLoader:
    """Loads plugin registry from YAML (or JSON fallback).

    Uses a lazy import seam — ``yaml`` is never imported at module level.
    Falls back to ``json`` if ``yaml`` is unavailable.
    """

    __slots__ = ()

    def load(self, path: str) -> tuple[PluginEntry, ...]:
        """Read *path* and return a frozen tuple of :class:`PluginEntry`."""
        raw = self._read_file(path)
        data = self._parse(path, raw)
        plugins = data if isinstance(data, list) else data.get("plugins", [])
        entries: list[PluginEntry] = []
        for item in plugins:
            entries.append(
                PluginEntry(
                    name=str(item.get("name", "")),
                    slot=str(item.get("slot", "")),
                    enabled=bool(item.get("enabled", True)),
                    version=str(item.get("version", "")),
                )
            )
        return tuple(entries)

    # ------------------------------------------------------------------
    @staticmethod
    def _read_file(path: str) -> str:
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    @staticmethod
    def _parse(path: str, raw: str) -> dict | list:  # type: ignore[type-arg]
        """Parse YAML with JSON fallback (lazy seam, no top-level import)."""
        try:
            import yaml  # type: ignore[import-untyped]  # lazy seam

            return yaml.safe_load(raw) or {}
        except ModuleNotFoundError:
            import json

            return json.loads(raw)


__all__ = ["PluginEntry", "PluginRegistryLoader"]

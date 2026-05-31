"""Governance plugin lifecycle — activation, hot-reload, and event emission."""

from __future__ import annotations

from governance_engine.plugin_lifecycle.manager import (
    ManagedPlugin,
    PluginLifecycleManager,
    get_plugin_lifecycle_manager,
)

__all__ = [
    "ManagedPlugin",
    "PluginLifecycleManager",
    "get_plugin_lifecycle_manager",
]

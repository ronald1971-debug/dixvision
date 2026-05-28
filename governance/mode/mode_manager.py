"""governance.mode.mode_manager — Re-export of the canonical ModeManager.

The manifest directory tree places mode_manager.py inside governance/mode/.
This module re-exports all public names from the flat governance.mode_manager
so both import paths work identically:

    from governance.mode_manager import ModeManager       # legacy
    from governance.mode.mode_manager import ModeManager   # manifest-canonical
"""

from __future__ import annotations

from governance.mode_manager import (
    ModeManager,
    SystemMode,
    get_mode_manager,
)

__all__ = [
    "ModeManager",
    "SystemMode",
    "get_mode_manager",
]

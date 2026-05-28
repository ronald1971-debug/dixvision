"""
cockpit.charter — cockpit module registration stub.

The cockpit is the operator's window into the system — it provides the
chat interface, LLM routing, voice paraphrasing, and credential management
surfaces. It has no independent charter (it is an interface, not a voice).

This module exists to be imported for side effects by cockpit.chat so that
the module-import graph records the cockpit as live. No charter is
registered here; the four system voices (INDIRA / DYON / GOVERNANCE /
COGNITIVE_GOVERNANCE) each register their own charters in their respective
charter modules.
"""

from __future__ import annotations

# No charter registered — cockpit is an interface, not a voice.
# The operator speaks through this surface; the system speaks through
# INDIRA / DYON / GOVERNANCE / COGNITIVE_GOVERNANCE.

__all__: list[str] = []

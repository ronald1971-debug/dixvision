"""evolution_engine.charter — DYON's self-declared engineering intelligence charter.

Importing this package registers DYON's charter with the core charter registry.
The charter is immutable at runtime; amendments require a SYSTEM/CHARTER_AMENDED
governance event with operator approval.
"""

from evolution_engine.charter.dyon import DYON_CHARTER

__all__ = ["DYON_CHARTER"]

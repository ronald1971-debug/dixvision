"""
system_governance — Runtime structural integrity layer.

Priority in the architecture:
  - Development phases: P4 (lowest — cognitive integrity comes first)
  - Live deployment:    P4

Protections:
  1. Contract Integrity     — inter-subsystem contracts honoured at runtime
  2. Topology Guard         — no illegal cross-domain imports (B1 constraint)
  3. Runtime Consistency    — shared state consistent across subsystems
  4. Replay Integrity       — events deterministically replayable (INV-15)
  5. Convergence Monitor    — subsystems wiring up, not drifting apart
  6. Dependency Validator   — declared dependencies match runtime reality
"""

from system_governance.engine import SystemGovernanceEngine, get_system_governance

__all__ = ["SystemGovernanceEngine", "get_system_governance"]

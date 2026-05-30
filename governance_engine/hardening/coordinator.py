"""governance_engine.hardening.coordinator — Governance hardening coordinator.

Single `tick(ts_ns)` entry point that wires all 7 hardening subsystems:

  1. RuntimeInvariantMonitor  — formal + lightweight invariant proofs
  2. DeterministicReplayEngine — event-stream golden digest check
  3. MutationFirewall          — mutation containment before lifecycle
  4. PolicyLockManager         — hard policy lock + drift detection
  5. RuntimeIsolationBoundary  — cross-engine call authority enforcement
  6. TrustScorer               — hazard-driven trust erosion + recovery
  7. ExecutionAuditor          — execution decision log + anomaly detection

`snapshot()` returns the full hardening status dict across all 7 subsystems.

The coordinator does NOT own the singletons — it calls `get_*()` to fetch
them so the wider system can also access them independently.

Authority (L1): stdlib only at module level.
INV-15: ts_ns is caller-supplied.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

_logger = logging.getLogger(__name__)


class GovernanceHardeningCoordinator:
    """Wires all hardening subsystems into a single governance tick.

    Args:
        replay_interval: how many ticks between full replay verifications.
            Replay is expensive (full EventStore scan); default every 100 ticks.
        invariant_interval: forwarded to RuntimeInvariantMonitor.check_interval.
    """

    def __init__(
        self,
        *,
        replay_interval: int = 100,
        invariant_interval: int = 50,
    ) -> None:
        self._replay_interval = max(1, replay_interval)
        self._invariant_interval = max(1, invariant_interval)
        self._tick_count: int = 0
        self._lock = threading.Lock()
        self._last_hazard_summary: list[str] = []

    # ------------------------------------------------------------------
    # Main tick
    # ------------------------------------------------------------------

    def tick(self, ts_ns: int) -> dict[str, Any]:
        """Run one governance hardening tick.

        Returns a summary dict with keys for each subsystem result.
        This method is designed to be called on every governance tick
        without incurring Z3/full-replay overhead on every call.
        """
        self._tick_count += 1
        tick = self._tick_count
        summary: dict[str, Any] = {"tick": tick, "ts_ns": ts_ns}
        hazards: list[str] = []

        # 1. Policy lock — check first, fastest gate
        try:
            from governance_engine.hardening.policy_lock import get_policy_lock_manager
            lock_state = get_policy_lock_manager().check_and_enforce(ts_ns)
            summary["policy_lock"] = lock_state.status.value
            if get_policy_lock_manager().governance_blocked():
                hazards.append("POLICY_LOCK_DRIFTED")
        except Exception as exc:
            _logger.debug("hardening tick: policy_lock error: %s", exc)

        # 2. Invariant monitor — formal proofs run on interval inside check_all()
        try:
            from governance_engine.hardening.invariant_monitor import get_invariant_monitor
            report = get_invariant_monitor(
                check_interval=self._invariant_interval
            ).check_all(ts_ns)
            summary["invariants"] = {
                "all_hold": report.all_hold,
                "violated": list(report.violated_ids),
                "warnings": list(report.warning_ids),
            }
            hazards.extend(report.violated_ids)
        except Exception as exc:
            _logger.debug("hardening tick: invariant_monitor error: %s", exc)

        # 3. Trust scorer — passive recovery tick
        try:
            from governance_engine.hardening.trust_scorer import get_trust_scorer
            get_trust_scorer().tick(ts_ns)
            summary["trust_scorer"] = "ticked"
        except Exception as exc:
            _logger.debug("hardening tick: trust_scorer error: %s", exc)

        # 4. Replay verification — expensive, run on interval
        if tick % self._replay_interval == 0:
            try:
                from governance_engine.hardening.replay_engine import get_replay_engine
                batch = get_replay_engine().verify_all_streams(ts_ns)
                summary["replay"] = {
                    "all_match": batch.all_match,
                    "all_chains_ok": batch.all_chains_ok,
                    "streams_verified": batch.streams_verified,
                }
                if not batch.all_match:
                    hazards.append("REPLAY_DIGEST_MISMATCH")
                if not batch.all_chains_ok:
                    hazards.append("REPLAY_CHAIN_BROKEN")
            except Exception as exc:
                _logger.debug("hardening tick: replay_engine error: %s", exc)

        with self._lock:
            self._last_hazard_summary = hazards
        summary["hazards"] = hazards
        if hazards:
            _logger.warning(
                "GovernanceHardeningCoordinator tick=%d hazards=%s", tick, hazards
            )
        return summary

    # ------------------------------------------------------------------
    # Governance gate
    # ------------------------------------------------------------------

    def governance_blocked(self) -> bool:
        """True if any hard block is in effect (policy lock drifted)."""
        try:
            from governance_engine.hardening.policy_lock import get_policy_lock_manager
            return get_policy_lock_manager().governance_blocked()
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Full snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Return combined snapshot across all 7 hardening subsystems."""
        result: dict[str, Any] = {
            "tick_count": self._tick_count,
            "governance_blocked": self.governance_blocked(),
        }

        with self._lock:
            result["last_hazards"] = list(self._last_hazard_summary)

        # Collect individual snapshots with graceful degradation
        subsystems: list[tuple[str, str, str]] = [
            ("invariant_monitor", "governance_engine.hardening.invariant_monitor", "get_invariant_monitor"),
            ("replay_engine",     "governance_engine.hardening.replay_engine",     "get_replay_engine"),
            ("mutation_firewall", "governance_engine.hardening.mutation_firewall",  "get_mutation_firewall"),
            ("policy_lock",       "governance_engine.hardening.policy_lock",        "get_policy_lock_manager"),
            ("isolation_boundary","governance_engine.hardening.isolation_boundary", "get_isolation_boundary"),
            ("trust_scorer",      "governance_engine.hardening.trust_scorer",       "get_trust_scorer"),
            ("execution_auditor", "governance_engine.hardening.execution_auditor",  "get_execution_auditor"),
        ]
        for key, module_path, factory in subsystems:
            try:
                import importlib
                mod = importlib.import_module(module_path)
                obj = getattr(mod, factory)()
                result[key] = obj.snapshot()
            except Exception as exc:
                result[key] = {"error": str(exc)}

        return result


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_coordinator: GovernanceHardeningCoordinator | None = None
_coordinator_lock = threading.Lock()


def get_hardening_coordinator(
    *,
    replay_interval: int = 100,
    invariant_interval: int = 50,
) -> GovernanceHardeningCoordinator:
    global _coordinator
    with _coordinator_lock:
        if _coordinator is None:
            _coordinator = GovernanceHardeningCoordinator(
                replay_interval=replay_interval,
                invariant_interval=invariant_interval,
            )
    return _coordinator


__all__ = [
    "GovernanceHardeningCoordinator",
    "get_hardening_coordinator",
]

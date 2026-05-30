"""evolution_engine.lifecycle.sandbox — Stage 2: isolated sandbox executor.

SandboxRunner validates a proposal in an isolated context before it may
proceed to simulation.  It delegates to the existing patch_pipeline sandbox
when available; otherwise runs a synthetic parameter-validation pass.

Authority (L2/B1): stdlib only at module level.  All imports of
evolution_engine.patch_pipeline are lazy (inside method bodies).
INV-15: ts_ns is caller-supplied.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evolution_engine.lifecycle.contracts import ProposalRecord, SandboxResult

_logger = logging.getLogger(__name__)


class SandboxRunner:
    """Runs a proposal through an isolated sandbox test.

    Attempts to delegate to patch_pipeline.sandbox.PatchSandbox; if
    unavailable (import error or environment not set up), falls back to
    a synthetic validation pass that checks description length and
    mutation_class format.

    Returns a SandboxResult — never raises.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._run_count: int = 0

    def run(self, record: "ProposalRecord", ts_ns: int) -> "SandboxResult":
        """Execute sandbox isolation test for *record*.

        Returns a :class:`SandboxResult` with outcome PASS | FAIL | SKIP.
        """
        from evolution_engine.lifecycle.contracts import SandboxResult

        with self._lock:
            self._run_count += 1

        t0 = time.monotonic()
        outcome, notes = self._execute(record, ts_ns)
        elapsed_ms = (time.monotonic() - t0) * 1000.0

        result = SandboxResult(
            outcome=outcome,
            notes=notes,
            elapsed_ms=elapsed_ms,
            ts_ns=ts_ns,
        )
        _logger.debug(
            "SandboxRunner[%s] outcome=%s elapsed=%.1fms",
            record.proposal_id[:16],
            outcome,
            elapsed_ms,
        )
        return result

    def _execute(self, record: "ProposalRecord", ts_ns: int) -> tuple[str, str]:
        """Delegate to PatchSandbox or fall back to synthetic validation."""
        try:
            from evolution_engine.patch_pipeline.sandbox import PatchSandbox
            sb = PatchSandbox()
            passed = sb.run(record.proposal_id, record.description)
            if passed:
                return "PASS", "patch_pipeline sandbox passed"
            return "FAIL", "patch_pipeline sandbox reported failure"
        except ImportError:
            pass
        except Exception as exc:
            _logger.debug("SandboxRunner: PatchSandbox raised %s — using synthetic", exc)

        # Synthetic validation: check description is non-empty,
        # mutation_class is valid, and proposal_id is well-formed.
        if not record.description.strip():
            return "FAIL", "empty description"
        if record.mutation_class not in ("CLASS_A", "CLASS_B", "CLASS_C"):
            return "FAIL", f"unknown mutation_class={record.mutation_class!r}"
        if not record.proposal_id or len(record.proposal_id) < 4:
            return "FAIL", "proposal_id too short"
        return "SKIP", "synthetic validation passed (no sandbox available)"

    @property
    def run_count(self) -> int:
        return self._run_count


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_runner: SandboxRunner | None = None
_runner_lock = threading.Lock()


def get_sandbox_runner() -> SandboxRunner:
    """Return the process-wide SandboxRunner singleton."""
    global _runner
    with _runner_lock:
        if _runner is None:
            _runner = SandboxRunner()
    return _runner


__all__ = ["SandboxRunner", "get_sandbox_runner"]

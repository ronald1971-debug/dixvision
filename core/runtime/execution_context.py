"""
core/runtime/execution_context.py
Thread-local execution context. Carries trace_id + domain for
observability propagation.

INV-15 note: live-mode trace IDs use UUID4 for uniqueness; replay-mode
callers MUST use ``deterministic_trace_id()`` so that replays of the same
event stream produce identical trace IDs and spans can be correlated
across runs.
"""

from __future__ import annotations

import hashlib
import threading
import uuid
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExecutionContext:
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    domain: str = "SYSTEM"  # "MARKET" for Indira, "SYSTEM" for Dyon, "GOV" for governance
    component: str = "unknown"


_local = threading.local()


def new_trace_id() -> str:
    """Return a fresh non-deterministic trace ID (live-mode only).

    Do NOT call this during replay — use ``deterministic_trace_id()``
    instead so replayed spans carry the same IDs across runs (INV-15).
    """
    return uuid.uuid4().hex


def deterministic_trace_id(ts_ns: int, component: str, domain: str) -> str:
    """Return a SHA-256 trace ID that is stable across process restarts.

    Given identical inputs this always produces the same 32-hex-char string,
    satisfying the replay-determinism invariant (INV-15). Callers in the
    replay path must supply the original ``ts_ns`` from the persisted event,
    not the wall clock.
    """
    raw = f"{ts_ns}:{component}:{domain}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def set_context(ctx: ExecutionContext) -> None:
    _local.ctx = ctx


def get_context() -> ExecutionContext:
    ctx: ExecutionContext | None = getattr(_local, "ctx", None)
    if ctx is None:
        ctx = ExecutionContext()
        _local.ctx = ctx
    return ctx

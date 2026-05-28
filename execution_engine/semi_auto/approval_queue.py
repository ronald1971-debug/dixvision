"""Semi-auto approval queue (BUILD-DIRECTIVE §8).

FIFO queue of pending operator approvals for SEMI_AUTO domains.
Entries that require approval are pushed here and wait for the
operator to approve/reject via the dashboard.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class PendingApproval:
    """A queued order waiting for operator approval."""

    request_id: str
    domain: str
    symbol: str
    side: str
    notional_usd: float
    rationale: str
    ts_ns: int
    intent: Any = None


@dataclass
class ApprovalQueue:
    """FIFO queue for semi-auto pending approvals.

    Thread-safe access via the governance runtime's event loop.
    No locking needed in single-threaded async context.
    """

    _queue: deque[PendingApproval] = field(default_factory=deque)
    _history: list[tuple[str, str]] = field(default_factory=list)

    def push(self, approval: PendingApproval) -> None:
        """Add a pending approval to the queue."""
        self._queue.append(approval)

    def peek(self) -> PendingApproval | None:
        """View the next pending approval without removing it."""
        if not self._queue:
            return None
        return self._queue[0]

    def approve(self, request_id: str) -> PendingApproval | None:
        """Approve and remove an item by request_id."""
        for i, item in enumerate(self._queue):
            if item.request_id == request_id:
                del self._queue[i]
                self._history.append((request_id, "APPROVED"))
                return item
        return None

    def reject(self, request_id: str) -> PendingApproval | None:
        """Reject and remove an item by request_id."""
        for i, item in enumerate(self._queue):
            if item.request_id == request_id:
                del self._queue[i]
                self._history.append((request_id, "REJECTED"))
                return item
        return None

    def pending(self) -> list[PendingApproval]:
        """Return all pending approvals (read-only snapshot)."""
        return list(self._queue)

    @property
    def size(self) -> int:
        """Number of items in the queue."""
        return len(self._queue)

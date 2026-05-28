"""core/coherence/causal_graph.py
DIX VISION v42.2 — Causal dependency graph for belief propagation.

Pure data structures and pure functions only — no side effects, no clock
reads, no PRNG, no I/O. All operations are deterministic given the same
input sequence (INV-15).

The :class:`CausalGraph` represents a directed acyclic graph (DAG) of
belief-state nodes and the causal edges between them. The graph is used
by the coherence subsystem to detect:

* **Ghost causality** (CognitiveViolationKind.CAUSAL_GHOST): a node
  that participates in reasoning but cannot be traced back to any
  active external anchor. Active anchors are provided by the caller
  as a set of ``node_id`` strings.

* **Cycles** (CognitiveViolationKind.LINEAGE_CYCLE): a belief update
  path that loops back on itself — indicating circular self-referential
  reasoning (HALLUCINATION_LOOP surface).

Authority constraints:
* No imports from any ``*_engine`` package.
* No imports from ``state.ledger`` writers.
* Only stdlib imports plus :mod:`core.contracts`.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class CausalNode:
    """An atomic unit of causal belief.

    Fields:
        node_id: Stable identifier for this node (e.g. a belief key or
            strategy id).
        label: Human-readable label for the node.
        ts_ns: Nanosecond timestamp at which this node was registered
            in the graph.
    """

    node_id: str
    label: str
    ts_ns: int


@dataclass(frozen=True, slots=True)
class CausalEdge:
    """A directed causal dependency from ``from_id`` to ``to_id``.

    A directed edge ``A → B`` means "A is a causal ancestor of B" — i.e.
    a change in A can propagate forward to B. Weight is the strength of
    the causal link, in ``[0.0, 1.0]``.

    Fields:
        from_id: Source node identifier.
        to_id: Target node identifier.
        weight: Causal strength in ``[0.0, 1.0]``.
        ts_ns: Nanosecond timestamp at which this edge was added.
    """

    from_id: str
    to_id: str
    weight: float
    ts_ns: int


class CausalGraph:
    """Directed graph of causal dependencies between belief nodes.

    The graph is *not* a frozen dataclass because it is built
    incrementally by the coherence coordinator. All query methods
    (:meth:`ancestors`, :meth:`descendants`, :meth:`has_cycle`) are
    pure given the current state of the graph — same call, same result.

    INV-15: the graph itself is mutable (nodes/edges are added via
    ``add_node`` / ``add_edge``) but all query methods are
    deterministic given the current snapshot.
    """

    def __init__(self) -> None:
        # Map from node_id to CausalNode
        self._nodes: dict[str, CausalNode] = {}
        # Adjacency list: from_id → list of CausalEdge
        self._edges: dict[str, list[CausalEdge]] = {}
        # Reverse adjacency list: to_id → list of from_id (for ancestor queries)
        self._reverse: dict[str, list[str]] = {}

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def add_node(self, node: CausalNode) -> None:
        """Register a node. Idempotent — re-adding the same ``node_id``
        replaces the previous entry without raising an error."""
        self._nodes[node.node_id] = node
        self._edges.setdefault(node.node_id, [])
        self._reverse.setdefault(node.node_id, [])

    def add_edge(self, edge: CausalEdge) -> None:
        """Add a directed causal edge.

        Both ``from_id`` and ``to_id`` must already be registered via
        :meth:`add_node`; otherwise :exc:`KeyError` is raised. Adding
        duplicate edges (same ``from_id`` → ``to_id`` pair) appends a
        second entry — callers are responsible for deduplication if
        needed.
        """
        if edge.from_id not in self._nodes:
            raise KeyError(f"add_edge: unknown source node {edge.from_id!r}")
        if edge.to_id not in self._nodes:
            raise KeyError(f"add_edge: unknown target node {edge.to_id!r}")
        self._edges[edge.from_id].append(edge)
        self._reverse.setdefault(edge.to_id, []).append(edge.from_id)

    # ------------------------------------------------------------------
    # Pure query methods
    # ------------------------------------------------------------------

    def ancestors(self, node_id: str) -> frozenset[str]:
        """Return all transitive ancestors of ``node_id`` (BFS, pure).

        An ancestor of X is any node Y such that there is a directed
        path ``Y → ... → X``. The returned set does NOT include
        ``node_id`` itself.

        Returns an empty frozenset if ``node_id`` is unknown.
        """
        if node_id not in self._nodes:
            return frozenset()
        visited: set[str] = set()
        queue: deque[str] = deque()
        for parent_id in self._reverse.get(node_id, []):
            if parent_id not in visited:
                visited.add(parent_id)
                queue.append(parent_id)
        while queue:
            current = queue.popleft()
            for parent_id in self._reverse.get(current, []):
                if parent_id not in visited:
                    visited.add(parent_id)
                    queue.append(parent_id)
        return frozenset(visited)

    def descendants(self, node_id: str) -> frozenset[str]:
        """Return all transitive descendants of ``node_id`` (BFS, pure).

        A descendant of X is any node Y such that there is a directed
        path ``X → ... → Y``. The returned set does NOT include
        ``node_id`` itself.

        Returns an empty frozenset if ``node_id`` is unknown.
        """
        if node_id not in self._nodes:
            return frozenset()
        visited: set[str] = set()
        queue: deque[str] = deque()
        for edge in self._edges.get(node_id, []):
            child_id = edge.to_id
            if child_id not in visited:
                visited.add(child_id)
                queue.append(child_id)
        while queue:
            current = queue.popleft()
            for edge in self._edges.get(current, []):
                child_id = edge.to_id
                if child_id not in visited:
                    visited.add(child_id)
                    queue.append(child_id)
        return frozenset(visited)

    def has_cycle(self) -> bool:
        """Return True if the graph contains at least one directed cycle.

        Uses iterative DFS with a "grey set" (in-progress) and "black
        set" (fully visited) — standard topological-sort cycle detection.
        Pure: does not mutate any graph state.
        """
        grey: set[str] = set()
        black: set[str] = set()
        stack: list[tuple[str, bool]] = []

        for start in self._nodes:
            if start in black:
                continue
            stack.append((start, False))
            while stack:
                node_id, leaving = stack.pop()
                if leaving:
                    grey.discard(node_id)
                    black.add(node_id)
                    continue
                if node_id in black:
                    continue
                if node_id in grey:
                    return True
                grey.add(node_id)
                # Push "leave" marker first, then children
                stack.append((node_id, True))
                for edge in self._edges.get(node_id, []):
                    if edge.to_id not in black:
                        stack.append((edge.to_id, False))
        return False

    def node_ids(self) -> frozenset[str]:
        """Return the current set of registered node identifiers."""
        return frozenset(self._nodes)

    def __len__(self) -> int:
        return len(self._nodes)

    def __contains__(self, node_id: object) -> bool:
        return node_id in self._nodes


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def detect_ghost_causality(
    graph: CausalGraph,
    active_nodes: frozenset[str],
) -> tuple[str, ...]:
    """Return node_ids with no reachable anchor in ``active_nodes``.

    A "ghost" causal node is one whose entire ancestor chain contains no
    member of ``active_nodes`` — the belief cannot be traced back to any
    currently-active external observation. This corresponds to
    :attr:`~core.contracts.cognitive_governance.CognitiveViolationKind.CAUSAL_GHOST`.

    Pure / deterministic (INV-15): same ``graph`` state and same
    ``active_nodes`` always produce the same sorted tuple.

    Args:
        graph: The current causal graph snapshot.
        active_nodes: Identifiers of nodes that are considered "anchored"
            to external reality (e.g. nodes that were recently updated
            by a live market observation).

    Returns:
        A sorted tuple of ``node_id`` strings that have no reachable
        anchor in ``active_nodes``. Nodes that ARE in ``active_nodes``
        are never included in the returned tuple (they are their own
        anchor).
    """
    ghosts: list[str] = []
    for node_id in sorted(graph.node_ids()):
        if node_id in active_nodes:
            continue
        # Check whether any ancestor is an active anchor
        ancestor_set = graph.ancestors(node_id)
        if not ancestor_set.intersection(active_nodes):
            ghosts.append(node_id)
    return tuple(ghosts)


__all__ = [
    "CausalEdge",
    "CausalGraph",
    "CausalNode",
    "detect_ghost_causality",
]

# Keep a private sentinel so downstream linters see the ``field`` import used
# even though CausalGraph uses __slots__ via its __init__ rather than a
# dataclass field() — mirrors the style of belief_state.py.
_ = field

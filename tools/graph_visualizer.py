# ADAPTED FROM: WestHealth/pyvis + igraph/python-igraph
# (pyvis/network.py — Network.add_node(), add_edge(), show() → HTML;
#  igraph/Graph.py — Graph, community_multilevel(), betweenness())
"""C-86 — Interactive graph visualization for operator dashboard.

This module adapts ``pyvis`` and ``igraph`` for rendering causal graphs,
strategy lineage, and knowledge graphs as interactive HTML.

What survives from upstream (WestHealth/pyvis + igraph):
    * **Network** — ``network.py``: add_node(), add_edge(), show() for
      HTML output.
    * **Graph** — ``Graph.py``: community detection via multilevel
      Louvain, betweenness centrality.

What we replaced:
    * Real pyvis/igraph imports are lazy (Protocol seam).
    * In-memory graph representation for unit tests.
    * Export to HTML string or dict for embedding.

OFFLINE tier: visualization/analytics only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

NEW_PIP_DEPENDENCIES: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GraphNode:
    """A node in the visualization graph."""

    node_id: str
    label: str = ""
    group: str = ""
    size: float = 10.0


@dataclass(frozen=True, slots=True)
class GraphEdge:
    """An edge in the visualization graph."""

    source: str
    target: str
    weight: float = 1.0
    label: str = ""


@dataclass
class GraphData:
    """Container for graph nodes and edges."""

    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Export graph as serializable dict."""
        return {
            "nodes": [
                {"id": n.node_id, "label": n.label, "group": n.group, "size": n.size}
                for n in self.nodes
            ],
            "edges": [
                {"from": e.source, "to": e.target, "weight": e.weight, "label": e.label}
                for e in self.edges
            ],
        }


class GraphVisualizer:
    """Interactive graph visualizer for operator dashboard.

    Renders causal graph, strategy lineage, and knowledge graph as
    interactive HTML (pyvis) with community detection (igraph).

    Usage::

        viz = GraphVisualizer()
        viz.add_node("A", label="Strategy Alpha")
        viz.add_edge("A", "B", weight=0.9)
        html = viz.render_html()
    """

    def __init__(self, *, title: str = "DIX Graph", in_memory: bool = True) -> None:
        self._title = title
        self._in_memory = in_memory
        self._graph = GraphData()

    def add_node(
        self, node_id: str, *, label: str = "", group: str = "", size: float = 10.0
    ) -> None:
        """Add a node to the graph."""
        self._graph.nodes.append(
            GraphNode(node_id=node_id, label=label or node_id, group=group, size=size)
        )

    def add_edge(self, source: str, target: str, *, weight: float = 1.0, label: str = "") -> None:
        """Add an edge to the graph."""
        self._graph.edges.append(
            GraphEdge(source=source, target=target, weight=weight, label=label)
        )

    @property
    def node_count(self) -> int:
        return len(self._graph.nodes)

    @property
    def edge_count(self) -> int:
        return len(self._graph.edges)

    def detect_communities(self) -> dict[str, int]:
        """Detect communities using igraph Louvain (or fallback)."""
        if self._in_memory:
            return self._simple_community_detection()
        return self._igraph_communities()

    def render_html(self) -> str:
        """Render interactive HTML visualization."""
        if self._in_memory:
            return self._render_simple_html()
        return self._render_pyvis_html()

    def get_graph_data(self) -> GraphData:
        """Get raw graph data for serialization."""
        return self._graph

    # ---- fallback implementations ----------------------------------------

    def _simple_community_detection(self) -> dict[str, int]:
        """Simple connected-component based community detection."""
        adj: dict[str, set[str]] = {}
        for node in self._graph.nodes:
            adj.setdefault(node.node_id, set())
        for edge in self._graph.edges:
            adj.setdefault(edge.source, set()).add(edge.target)
            adj.setdefault(edge.target, set()).add(edge.source)

        visited: set[str] = set()
        communities: dict[str, int] = {}
        community_id = 0

        for node_id in adj:
            if node_id in visited:
                continue
            stack = [node_id]
            while stack:
                current = stack.pop()
                if current in visited:
                    continue
                visited.add(current)
                communities[current] = community_id
                for neighbor in adj.get(current, set()):
                    if neighbor not in visited:
                        stack.append(neighbor)
            community_id += 1

        return communities

    def _render_simple_html(self) -> str:
        """Render a minimal HTML representation."""
        import json

        data = self._graph.to_dict()
        return (
            f"<html><head><title>{self._title}</title></head>"
            f"<body><script>var graphData = {json.dumps(data)};</script>"
            f"<p>Nodes: {self.node_count}, Edges: {self.edge_count}</p>"
            f"</body></html>"
        )

    def _igraph_communities(self) -> dict[str, int]:
        """Community detection via igraph."""
        try:
            import igraph as ig

            g = ig.Graph(directed=False)
            node_ids = [n.node_id for n in self._graph.nodes]
            g.add_vertices(len(node_ids))
            id_map = {nid: i for i, nid in enumerate(node_ids)}
            edges = [
                (id_map[e.source], id_map[e.target])
                for e in self._graph.edges
                if e.source in id_map and e.target in id_map
            ]
            g.add_edges(edges)
            membership = g.community_multilevel().membership
            return {node_ids[i]: m for i, m in enumerate(membership)}
        except ImportError:
            return self._simple_community_detection()

    def _render_pyvis_html(self) -> str:
        """Render via pyvis Network."""
        try:
            from pyvis.network import Network

            net = Network(heading=self._title, height="600px", width="100%")
            for node in self._graph.nodes:
                net.add_node(node.node_id, label=node.label, group=node.group)
            for edge in self._graph.edges:
                net.add_edge(edge.source, edge.target, value=edge.weight)
            return net.generate_html()
        except ImportError:
            return self._render_simple_html()


__all__ = ["NEW_PIP_DEPENDENCIES", "GraphData", "GraphEdge", "GraphNode", "GraphVisualizer"]

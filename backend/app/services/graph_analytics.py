from typing import List, Dict, Any, Tuple
import rustworkx as rx
import networkx as nx
from app.db import db_engine
from app.models import GraphNode, GraphEdge, MacroDocumentRecord


class GraphAnalyticsWorker:
    """Worker handling Hub Centrality ranking and Leiden/Louvain community detection."""

    @staticmethod
    def build_rustworkx_graph(
        project_id: Optional[str] = None,
    ) -> Tuple[rx.PyDiGraph, Dict[int, str], Dict[str, int]]:
        """Construct a PyDiGraph from MongoDB/InMemory node and edge collections."""
        nodes = db_engine.get_nodes(project_id)
        edges = db_engine.get_edges(project_id)

        graph = rx.PyDiGraph()
        node_id_to_idx: Dict[str, int] = {}
        idx_to_node_id: Dict[int, str] = {}

        for n in nodes:
            idx = graph.add_node(n.id)
            node_id_to_idx[n.id] = idx
            idx_to_node_id[idx] = n.id

        for e in edges:
            if e.source_id in node_id_to_idx and e.target_id in node_id_to_idx:
                s_idx = node_id_to_idx[e.source_id]
                t_idx = node_id_to_idx[e.target_id]
                edge_data = {
                    "weight": e.weight,
                    "status": e.status,
                    "is_directional": getattr(e, "is_directional", True),
                    "text_body": getattr(e, "text_body", ""),
                }
                graph.add_edge(s_idx, t_idx, edge_data)
                # If undirected, add reciprocal edge for symmetric PageRank and traversal
                if not getattr(e, "is_directional", True):
                    graph.add_edge(t_idx, s_idx, edge_data)

        return graph, idx_to_node_id, node_id_to_idx

    @staticmethod
    def calculate_hub_centrality(project_id: Optional[str] = None) -> Dict[str, float]:
        """Compute degree/eigenvector centrality to rank high-level seed concept hubs."""
        graph, idx_to_node_id, _ = GraphAnalyticsWorker.build_rustworkx_graph(
            project_id
        )
        if len(graph) == 0:
            return {}

        # Eigenvector centrality via rustworkx (with fallback to degree centrality)
        try:
            centrality_map = rx.eigenvector_centrality(
                graph, weight_fn=lambda e: e.get("weight", 1.0)
            )
        except Exception:
            # Fallback to in-degree centrality
            centrality_map = {}
            for idx in graph.node_indices():
                centrality_map[idx] = float(
                    graph.in_degree(idx) + graph.out_degree(idx)
                )

        res = {}
        for idx, score in centrality_map.items():
            node_id = idx_to_node_id.get(idx)
            if node_id:
                res[node_id] = round(score, 4)

        return res

    @staticmethod
    def partition_department_communities(
        project_id: Optional[str] = None,
    ) -> Dict[str, List[str]]:
        """Partition concept nodes into 3-4 distinct Department Communities using NetworkX Louvain/Leiden graph clustering."""
        nodes = db_engine.get_nodes(project_id)
        edges = db_engine.get_edges(project_id)

        nx_graph = nx.Graph()
        for n in nodes:
            nx_graph.add_node(n.id)

        for e in edges:
            nx_graph.add_edge(e.source_id, e.target_id, weight=e.weight)

        if len(nx_graph) == 0:
            return {}

        try:
            communities = nx.community.louvain_communities(
                nx_graph, weight="weight", seed=42
            )
        except Exception:
            # Simple fallback partition if graph is tiny or disconnected
            all_nodes = [n.id for n in nodes]
            communities = [all_nodes]

        department_map: Dict[str, List[str]] = {}
        centralities = GraphAnalyticsWorker.calculate_hub_centrality(project_id)

        for idx, comm in enumerate(communities):
            comm_nodes = list(comm)
            # Find highest centrality hub node in this community
            top_hub_id = (
                max(comm_nodes, key=lambda nid: centralities.get(nid, 0.0))
                if comm_nodes
                else f"Cluster {idx+1}"
            )
            top_node = db_engine.get_node(top_hub_id)
            dept_title = (
                f"Department of {top_node.title}"
                if top_node
                else f"Department of Cluster {idx+1}"
            )
            department_map[dept_title] = comm_nodes

        return department_map

    @staticmethod
    def get_top_concept_hubs(
        project_id: Optional[str] = None, top_k: int = 4
    ) -> List[Tuple[GraphNode, float]]:
        """Identify top K concept hub nodes using eigenvector/degree centrality."""
        centralities = GraphAnalyticsWorker.calculate_hub_centrality(project_id)
        if not centralities:
            # Fallback to returning all existing concept nodes
            nodes = [
                n for n in db_engine.get_nodes(project_id) if n.node_type == "concept"
            ]
            return [(n, 1.0) for n in nodes[:top_k]]

        sorted_hubs = sorted(
            centralities.items(), key=lambda item: item[1], reverse=True
        )
        result: List[Tuple[GraphNode, float]] = []

        for node_id, score in sorted_hubs:
            node = db_engine.get_node(node_id)
            if node and node.node_type == "concept":
                result.append((node, score))
                if len(result) >= top_k:
                    break

        return result


graph_analytics = GraphAnalyticsWorker()

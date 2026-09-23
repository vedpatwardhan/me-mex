from typing import List, Dict, Any, Tuple
import rustworkx as rx
import networkx as nx
from app.db import db_engine
from app.models import GraphNode, GraphEdge, MacroDocumentRecord


class GraphAnalyticsWorker:
    """Worker handling Hub Centrality ranking and Leiden/Louvain community detection."""

    @staticmethod
    def build_rustworkx_graph(
        theme_id: Optional[str] = None,
    ) -> Tuple[rx.PyDiGraph, Dict[int, str], Dict[str, int]]:
        """Construct a PyDiGraph from MongoDB/InMemory node and edge collections."""
        nodes = db_engine.get_nodes(theme_id)
        edges = db_engine.get_edges(theme_id)

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
    def calculate_hub_centrality(theme_id: Optional[str] = None) -> Dict[str, float]:
        """Compute degree/eigenvector centrality to rank high-level seed concept hubs."""
        graph, idx_to_node_id, _ = GraphAnalyticsWorker.build_rustworkx_graph(theme_id)
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
        theme_id: Optional[str] = None,
    ) -> Dict[str, List[str]]:
        """Partition concept nodes into 3-4 distinct Department Communities using NetworkX Louvain/Leiden graph clustering."""
        nodes = db_engine.get_nodes(theme_id)
        edges = db_engine.get_edges(theme_id)

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
        centralities = GraphAnalyticsWorker.calculate_hub_centrality(theme_id)

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
    def update_macro_documents(theme_id: Optional[str] = None):
        """Update Macro Documents based on updated Leiden/Louvain community partitions."""
        partitions = GraphAnalyticsWorker.partition_department_communities(theme_id)
        centralities = GraphAnalyticsWorker.calculate_hub_centrality(theme_id)

        for dept_name, member_node_ids in partitions.items():
            # Rank hubs in this department
            dept_hubs = sorted(
                member_node_ids,
                key=lambda nid: centralities.get(nid, 0.0),
                reverse=True,
            )[:3]
            macro_id = (
                f"macro_{dept_name.lower().replace(' ', '_').replace('&', 'and')}"
            )

            macro_rec = MacroDocumentRecord(
                _id=macro_id,
                theme_id=theme_id or "vla_research",
                department_name=dept_name,
                hub_concept_ids=dept_hubs,
                summary_text=f"# Macro Department: {dept_name}\nCovers high-level concept hubs: {', '.join(dept_hubs)}.\nContains {len(member_node_ids)} total interlinked concepts.",
            )
            db_engine.upsert_macro(macro_rec)
        print(
            f"[GraphAnalyticsWorker] Successfully updated {len(partitions)} Department Macro Documents."
        )


graph_analytics = GraphAnalyticsWorker()

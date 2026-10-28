from typing import Optional
from typing import List, Dict, Any, Tuple
import rustworkx as rx
import networkx as nx
from app.db import db_engine
from app.models import GraphNode, GraphEdge, MacroDocumentRecord, ConceptHubCandidate


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
                    "weight": 1.0,  # Unweighted topological link (w=1.0)
                    "status": e.status,
                    "is_directional": getattr(e, "is_directional", True),
                    "description": getattr(e, "description", ""),
                }
                graph.add_edge(s_idx, t_idx, edge_data)
                # If undirected, add reciprocal edge for symmetric PageRank and traversal
                if not getattr(e, "is_directional", True):
                    graph.add_edge(t_idx, s_idx, edge_data)

        return graph, idx_to_node_id, node_id_to_idx

    @staticmethod
    def calculate_hub_centrality(project_id: Optional[str] = None) -> Dict[str, float]:
        """Compute unweighted eigenvector centrality via rustworkx to rank foundational concept hubs."""
        graph, idx_to_node_id, _ = GraphAnalyticsWorker.build_rustworkx_graph(
            project_id
        )
        if len(graph) == 0:
            return {}

        # Unweighted eigenvector centrality via rustworkx (with fallback to degree centrality)
        try:
            centrality_map = rx.eigenvector_centrality(graph, weight_fn=lambda e: 1.0)
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
        hubs: Optional[List[GraphNode]] = None,
        max_depth: int = 5,
    ) -> Dict[str, List[str]]:
        """Partition concept nodes into mutually exclusive Department Communities anchored to concept hubs using topological Voronoi distance.

        Nodes exceeding max_depth hops from a hub remain unassigned to preserve locality.
        """
        nodes = db_engine.get_nodes(project_id)
        if not nodes:
            return {}

        # If hubs not passed explicitly, discover top candidate mutable concept hubs
        if hubs is None:
            top_hub_tuples = GraphAnalyticsWorker.get_top_concept_hubs(project_id)
            hubs = [h[0] for h in top_hub_tuples]

        if not hubs:
            return {}

        edges = db_engine.get_edges(project_id)

        # Build undirected graph for topological distance metric
        nx_graph = nx.Graph()
        for n in nodes:
            nx_graph.add_node(n.id)

        for e in edges:
            nx_graph.add_edge(e.source_id, e.target_id, weight=1.0)

        hub_ids = [h.id for h in hubs]
        centralities = GraphAnalyticsWorker.calculate_hub_centrality(project_id)

        # Multi-source shortest path Voronoi partitioning bounded by max_depth:
        # Compute shortest topological path from each hub to reachable nodes within max_depth hops
        distances_from_hubs: Dict[str, Dict[str, int]] = {}
        for h_id in hub_ids:
            try:
                distances_from_hubs[h_id] = nx.single_source_shortest_path_length(
                    nx_graph, h_id, cutoff=max_depth
                )
            except Exception:
                distances_from_hubs[h_id] = {h_id: 0}

        department_map: Dict[str, List[str]] = {h_id: [] for h_id in hub_ids}

        # Assign each node to its closest department hub strictly within max_depth hops
        for n in nodes:
            best_hub = None
            best_dist = float("inf")
            best_score = -1.0

            for h_id in hub_ids:
                d = distances_from_hubs[h_id].get(n.id, float("inf"))
                if d > max_depth:
                    continue
                score = centralities.get(h_id, 0.0)

                # Minimize distance; break ties by highest hub centrality, then lexicographical order
                if d < best_dist:
                    best_dist = d
                    best_hub = h_id
                    best_score = score
                elif d == best_dist and score > best_score:
                    best_hub = h_id
                    best_score = score
                elif (
                    d == best_dist
                    and score == best_score
                    and best_hub
                    and h_id < best_hub
                ):
                    best_hub = h_id

            # Only assign if within max_depth (no unbounded fallback)
            if best_hub is not None and best_dist <= max_depth:
                department_map[best_hub].append(n.id)

        # Ensure the hub itself is in its own partition
        for h_id in hub_ids:
            if h_id not in department_map[h_id]:
                department_map[h_id].append(h_id)

        return department_map

    @staticmethod
    def get_top_concept_hubs(
        project_id: Optional[str] = None,
        max_k: int = 8,
        relative_threshold: float = 0.30,
    ) -> List[ConceptHubCandidate]:
        """Identify mutable domain concept hub nodes dynamically using eigenvector/degree centrality with relative thresholding."""
        # Filter candidate concept hubs: strictly Mutable Concepts (excludes Root Nodes & Immutable Intra-Document Concepts)
        all_nodes = db_engine.get_nodes(project_id)
        mutable_concept_hubs = [
            n
            for n in all_nodes
            if n.node_type.lower() == "concept" and not n.is_immutable
        ]

        # If no mutable concept hubs exist, return empty (never fallback to immutable concept nodes or root nodes)
        if not mutable_concept_hubs:
            return []

        centralities = GraphAnalyticsWorker.calculate_hub_centrality(project_id)

        # Filter scores strictly for candidate concept hubs
        concept_scores: List[Tuple[GraphNode, float]] = []
        for c_node in mutable_concept_hubs:
            score = centralities.get(c_node.id, 0.0)
            concept_scores.append((c_node, score))

        # Sort descending by centrality score
        concept_scores.sort(key=lambda x: x[1], reverse=True)

        if not concept_scores:
            return []

        max_score = concept_scores[0][1]

        # Apply relative thresholding (s_i >= relative_threshold * max_score)
        selected_hubs: List[ConceptHubCandidate] = []
        for c_node, score in concept_scores:
            # Always include the top hub; for others, enforce relative thresholding
            if not selected_hubs or score >= (max_score * relative_threshold):
                selected_hubs.append(
                    ConceptHubCandidate(node=c_node, centrality_score=score)
                )
                if len(selected_hubs) >= max_k:
                    break

        # GUARANTEE: The primordial Universal Genesis node ('Everything') must ALWAYS be present in candidate hubs
        genesis_node = db_engine.get_genesis_node(project_id)
        if genesis_node:
            selected_ids = {h.id for h in selected_hubs}
            if genesis_node.id not in selected_ids:
                genesis_score = centralities.get(genesis_node.id, 0.0)
                selected_hubs.append(
                    ConceptHubCandidate(
                        node=genesis_node, centrality_score=genesis_score
                    )
                )

        return selected_hubs


graph_analytics = GraphAnalyticsWorker()

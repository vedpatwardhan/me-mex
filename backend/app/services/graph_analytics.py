from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx
import rustworkx as rx

from app.db import db_engine
from app.models import GraphEdge, GraphNode
from app.services.graph_link_utils import (
    MUTABLE_PARENT_META_KEY,
    legacy_infer_mutable_parent_id,
    migrate_legacy_mutable_parent_metadata,
)


class MutableTreeIndex:
    """
    Mutable concept backbone rooted at Genesis.

    Parent/child links are stored in node metadata (`mutable_parent_id`); graph edges
    are unweighted and undifferentiated for adjacency.
    """

    def __init__(
        self,
        project_id: Optional[str] = None,
        nodes: Optional[List[GraphNode]] = None,
        edges: Optional[List[GraphEdge]] = None,
    ):
        self.project_id = project_id
        self.nodes = nodes if nodes is not None else db_engine.get_nodes(project_id)
        self.edges = edges if edges is not None else db_engine.get_edges(project_id)
        self.node_map: Dict[str, GraphNode] = {n.id: n for n in self.nodes}
        self.genesis_id: Optional[str] = None
        for n in self.nodes:
            if n.metadata.get("is_genesis") or n.title.strip().lower() == "everything":
                self.genesis_id = n.id
                break

        self._parent: Dict[str, str] = {}
        self._mutable_children: Dict[str, List[str]] = {}
        self._direct_neighbors: Dict[str, List[str]] = {}
        self._build_mutable_tree()

        self.tree_depth_from_genesis: Dict[str, int] = {}
        self.subtree_mut_height: Dict[str, int] = {}
        self.strahler_order: Dict[str, int] = {}
        self.subtree_immutable_count: Dict[str, int] = {}
        self._compute_metrics()

    def _build_mutable_tree(self) -> None:
        for e in self.edges:
            self._direct_neighbors.setdefault(e.source_id, []).append(e.target_id)
            self._direct_neighbors.setdefault(e.target_id, []).append(e.source_id)

        for n in self.nodes:
            if n.is_immutable or n.is_root_node:
                continue
            parent_id = n.metadata.get(MUTABLE_PARENT_META_KEY)
            if not parent_id:
                parent_id = legacy_infer_mutable_parent_id(
                    n.id, self.edges, self.node_map
                )
            if not parent_id:
                continue
            parent = self.node_map.get(parent_id)
            if not parent or parent.is_immutable:
                continue
            child_id = n.id
            if child_id in self._parent and self._parent[child_id] != parent_id:
                continue
            self._parent[child_id] = parent_id
            self._mutable_children.setdefault(parent_id, []).append(child_id)

        for pid, kids in self._mutable_children.items():
            self._mutable_children[pid] = sorted(set(kids))

    def parent_of(self, node_id: str) -> Optional[str]:
        return self._parent.get(node_id)

    def mutable_children(self, node_id: str) -> List[GraphNode]:
        ids = self._mutable_children.get(node_id, [])
        return [self.node_map[i] for i in ids if i in self.node_map]

    def mutable_siblings(self, node_id: str) -> List[GraphNode]:
        parent_id = self.parent_of(node_id)
        if not parent_id:
            return []
        return [n for n in self.mutable_children(parent_id) if n.id != node_id]

    def degree(self, node_id: str) -> int:
        return len(self._direct_neighbors.get(node_id, []))

    def effective_degree(self, node_id: str) -> int:
        """Direct non-root neighbors (includes tree parent)."""
        count = 0
        for nid in self._direct_neighbors.get(node_id, []):
            n = self.node_map.get(nid)
            if n and n.is_root_node:
                continue
            count += 1
        return count

    def partition_neighbor_count(self, node_id: str) -> int:
        """Neighbors in a partition batch (excludes tree parent and ROOT)."""
        from app.services.reorg_rewire_utils import partition_neighbor_count

        return partition_neighbor_count(node_id, self.project_id)

    def direct_immutable_neighbors(self, node_id: str) -> List[GraphNode]:
        imm: List[GraphNode] = []
        seen: Set[str] = set()
        for nid in self._direct_neighbors.get(node_id, []):
            if nid in seen:
                continue
            seen.add(nid)
            n = self.node_map.get(nid)
            if n and n.is_immutable and not n.is_root_node:
                imm.append(n)
        return imm

    def ancestors(self, node_id: str) -> List[str]:
        chain: List[str] = []
        cur = self.parent_of(node_id)
        while cur:
            chain.append(cur)
            cur = self.parent_of(cur)
        return chain

    def path_to_genesis(self, node_id: str) -> List[str]:
        if not self.genesis_id:
            return [node_id]
        path = [node_id]
        cur = node_id
        while cur != self.genesis_id:
            p = self.parent_of(cur)
            if not p:
                break
            path.append(p)
            cur = p
        if path[-1] != self.genesis_id and self.genesis_id:
            path.append(self.genesis_id)
        return path

    def _compute_metrics(self) -> None:
        if not self.genesis_id:
            return

        def mut_height(nid: str, visiting: Set[str]) -> int:
            if nid in visiting:
                return 0
            visiting.add(nid)
            kids = [
                c
                for c in self._mutable_children.get(nid, [])
                if c in self.node_map and not self.node_map[c].is_immutable
            ]
            if not kids:
                self.subtree_mut_height[nid] = 0
                return 0
            h = 1 + max(mut_height(c, visiting) for c in kids)
            self.subtree_mut_height[nid] = h
            return h

        mut_height(self.genesis_id, set())

        def depth_from_genesis(nid: str) -> int:
            d = 0
            cur = nid
            while cur and cur != self.genesis_id:
                p = self.parent_of(cur)
                if not p:
                    return d
                d += 1
                cur = p
            return d

        for n in self.nodes:
            if n.is_immutable or n.is_root_node:
                continue
            self.tree_depth_from_genesis[n.id] = depth_from_genesis(n.id)
            self.strahler_order[n.id] = self._strahler(n.id)
            self.subtree_immutable_count[n.id] = self._count_immutables(n.id)

    def _strahler(self, nid: str) -> int:
        kids = self._mutable_children.get(nid, [])
        if not kids:
            return 1
        child_orders = [self._strahler(c) for c in kids]
        child_orders.sort(reverse=True)
        if len(child_orders) >= 2 and child_orders[0] == child_orders[1]:
            return child_orders[0] + 1
        return max(child_orders) if child_orders else 1

    def _count_immutables(self, nid: str, seen: Optional[Set[str]] = None) -> int:
        if seen is None:
            seen = set()
        if nid in seen:
            return 0
        seen.add(nid)
        count = len(self.direct_immutable_neighbors(nid))
        for c in self._mutable_children.get(nid, []):
            count += self._count_immutables(c, seen)
        return count

    def sackin_index(self) -> int:
        total = 0
        for n in self.nodes:
            if n.is_immutable and not n.is_root_node:
                parent_edges = [
                    e
                    for e in self.edges
                    if (e.source_id == n.id or e.target_id == n.id)
                ]
                depth = 1
                for e in parent_edges:
                    other = e.target_id if e.source_id == n.id else e.source_id
                    if other in self.node_map and not self.node_map[other].is_immutable:
                        depth = 1 + self.tree_depth_from_genesis.get(other, 0)
                        break
                total += depth
        return total

    def immutable_reachability_within_k(self, k: int = 3) -> float:
        if not self.genesis_id:
            return 0.0
        imm_nodes = [n for n in self.nodes if n.is_immutable and not n.is_root_node]
        if not imm_nodes:
            return 100.0
        g = nx.Graph()
        g.add_node(self.genesis_id)
        for e in self.edges:
            g.add_edge(e.source_id, e.target_id)
        reachable = 0
        try:
            lengths = nx.single_source_shortest_path_length(
                g, self.genesis_id, cutoff=k
            )
        except Exception:
            return 0.0
        for n in imm_nodes:
            if n.id in lengths:
                reachable += 1
        return round(100.0 * reachable / len(imm_nodes), 2)

    def health_metrics(self, k: int = 3) -> Dict[str, Any]:
        max_depth = max(self.tree_depth_from_genesis.values(), default=0)
        max_deg = max(
            (self.degree(n.id) for n in self.nodes if not n.is_immutable), default=0
        )
        return {
            "max_mutable_depth": max_depth,
            "max_mutable_degree": max_deg,
            "sackin_index": self.sackin_index(),
            "immutable_reachable_pct_within_k": self.immutable_reachability_within_k(k),
            "hop_k": k,
        }

    def recompute_and_persist_metadata(self) -> None:
        for n in self.nodes:
            if n.is_immutable or n.is_root_node:
                continue
            direct_imm = [m.id for m in self.direct_immutable_neighbors(n.id)]
            meta = dict(n.metadata)
            meta["tree_depth_from_genesis"] = self.tree_depth_from_genesis.get(n.id, 0)
            meta["subtree_mut_height"] = self.subtree_mut_height.get(n.id, 0)
            meta["strahler_order"] = self.strahler_order.get(n.id, 1)
            meta["subtree_immutable_count"] = self.subtree_immutable_count.get(n.id, 0)
            meta["direct_immutable_neighbor_ids"] = direct_imm
            meta.pop("miscellaneous_immutable_ids", None)
            n.metadata = meta
            n.updated_at = __import__("time").time()
            db_engine.upsert_node(n)


@dataclass
class GraphAnalyticsWorker:
    """Tree index and graph health metrics (v0.2 — no eigenvector / Voronoi partitioning)."""

    @staticmethod
    def build_rustworkx_graph(
        project_id: Optional[str] = None,
    ) -> Tuple[rx.PyDiGraph, Dict[int, str], Dict[str, int]]:
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
                    "weight": 1.0,
                    "status": e.status,
                    "is_directional": getattr(e, "is_directional", True),
                    "description": getattr(e, "description", ""),
                }
                graph.add_edge(s_idx, t_idx, edge_data)
                if not getattr(e, "is_directional", True):
                    graph.add_edge(t_idx, s_idx, edge_data)
        return graph, idx_to_node_id, node_id_to_idx

    @staticmethod
    def build_tree_index(project_id: Optional[str] = None) -> MutableTreeIndex:
        return MutableTreeIndex(project_id=project_id)

    @staticmethod
    def refresh_tree_metadata(project_id: Optional[str] = None) -> Dict[str, Any]:
        migrate_legacy_mutable_parent_metadata(project_id)
        idx = MutableTreeIndex(project_id=project_id)
        idx.recompute_and_persist_metadata()
        return idx.health_metrics()


graph_analytics = GraphAnalyticsWorker()

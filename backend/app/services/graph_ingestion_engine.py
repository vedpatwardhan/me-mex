"""
Graph Ingestion & Command Execution Engine: Me-Mex v0.2
"""

import uuid
import time
from typing import List, Dict, Any, Optional, Set

from app.config import settings
from app.db import db_engine
from app.models import GraphNode, GraphEdge
from app.services.event_queue import event_queue
from app.services.graph_analytics import MutableTreeIndex, graph_analytics


def _is_genesis(node: GraphNode) -> bool:
    return bool(
        node.metadata.get("is_genesis") or node.title.strip().lower() == "everything"
    )


class GraphIngestionEngine:
    """Zero-consensus command execution with engine-dispatch reorganization commits."""

    def __init__(self):
        self.db = db_engine
        self.event_queue = event_queue

    def execute_single_command(
        self,
        item: Dict[str, Any],
        doc_title: str,
        proj_list: List[str],
    ) -> Optional[Dict[str, Any]]:
        action = item.get("action") or item.get("command_type")
        dept_name = item.get("navigator_name") or item.get(
            "department_name", "Graph Navigator"
        )
        persona_id = item.get("navigator_id") or item.get("persona_id")

        if action in ["CREATE_EDGE", "CONNECT_DIRECT", "CONSTRUCT_EDGE"]:
            return self._create_edge(item, proj_list, dept_name, persona_id)

        if action in ["CREATE_INTERMEDIATE", "CREATE_CONCEPT"]:
            return self._create_intermediate(item, proj_list, dept_name, persona_id)

        if action == "EDIT_CONCEPT":
            return self._edit_concept(item, dept_name, persona_id)

        if action == "SPLIT_CONCEPT":
            return self._split_concept(item, proj_list, dept_name, persona_id)

        return None

    def _create_edge(self, item, proj_list, dept_name, persona_id):
        edge_data = item.get("edge", {})
        src_id = edge_data.get("source_id")
        tgt_id = edge_data.get("target_id")
        if not (src_id and tgt_id):
            return None
        project_scope = proj_list[0] if proj_list else None
        for existing in self.db.get_edges(project_scope):
            if (existing.source_id == src_id and existing.target_id == tgt_id) or (
                existing.source_id == tgt_id and existing.target_id == src_id
            ):
                return None

        link_class = (
            edge_data.get("link_class") or item.get("link_class") or "clustered"
        )
        edge_id = f"edge_{uuid.uuid4().hex[:8]}"
        edge_obj = GraphEdge(
            _id=edge_id,
            source_id=src_id,
            target_id=tgt_id,
            description=edge_data.get("description", "RELEVANT_TO"),
            project_ids=proj_list,
            metadata={"link_class": link_class},
        )
        self.db.upsert_edge(edge_obj)
        tgt_node = self.db.get_node(tgt_id)
        src_node = self.db.get_node(src_id)
        return {
            "event": "node_touched",
            "persona_id": persona_id,
            "persona_name": dept_name,
            "node_id": tgt_id,
            "node_title": tgt_node.title if tgt_node else tgt_id,
            "message": f"Connected '{src_node.title if src_node else src_id}' -> '{tgt_node.title if tgt_node else tgt_id}'.",
            "timestamp": time.time(),
        }

    def _create_intermediate(self, item, proj_list, dept_name, persona_id):
        concept_data = item.get("concept", {})
        c_title = concept_data.get("title")
        if not c_title:
            return None
        c_id = f"concept_{uuid.uuid4().hex[:8]}"
        new_node = GraphNode(
            _id=c_id,
            node_type="CONCEPT",
            title=c_title,
            description=concept_data.get("description", ""),
            passage_ids=concept_data.get("passage_ids", []),
            project_ids=proj_list,
            metadata={"immutable": False, "status": "PRIMARY_ACTIVE"},
        )
        self.db.upsert_node(new_node)
        for edge_info in item.get("edges", []):
            edge_obj = GraphEdge(
                _id=f"edge_{uuid.uuid4().hex[:8]}",
                source_id=edge_info.get("source_id", c_id),
                target_id=edge_info.get("target_id", c_id),
                description=edge_info.get("description", "SUBSET_OF"),
                project_ids=proj_list,
            )
            self.db.upsert_edge(edge_obj)
        return {
            "event": "node_touched",
            "persona_id": persona_id,
            "persona_name": dept_name,
            "node_id": c_id,
            "node_title": c_title,
            "message": f"Created intermediate concept '{c_title}'.",
            "timestamp": time.time(),
        }

    def _edit_concept(self, item, dept_name, persona_id):
        concept_data = item.get("concept", {})
        target_id = concept_data.get("id")
        if not target_id:
            return None
        target_node = self.db.get_node(target_id)
        if not target_node or target_node.is_immutable:
            return None
        new_title = concept_data.get("title")
        if new_title and not _is_genesis(target_node):
            target_node.title = new_title
        if concept_data.get("description") is not None:
            target_node.description = concept_data.get(
                "description", target_node.description
            )
        target_node.updated_at = time.time()
        self.db.upsert_node(target_node)
        return {
            "event": "node_touched",
            "persona_id": persona_id,
            "persona_name": dept_name,
            "node_id": target_id,
            "node_title": target_node.title,
            "message": f"Edited concept '{target_node.title}'.",
            "timestamp": time.time(),
        }

    def _split_concept(self, item, proj_list, dept_name, persona_id):
        concept_id = item.get("concept_id") or item.get("concept", {}).get("id")
        if not concept_id:
            return None
        target_node = self.db.get_node(concept_id)
        if not target_node or target_node.is_immutable:
            return None
        sub_concepts = item.get("sub_concepts", [])
        rewired_edges = item.get("rewired_edges", [])
        if not sub_concepts:
            return None

        project_scope = proj_list[0] if proj_list else None
        if _is_genesis(target_node):
            evt = self._apply_wrapper_split(
                target_node, sub_concepts, rewired_edges, item, proj_list, project_scope
            )
        else:
            evt = self._apply_lateral_split(
                target_node, sub_concepts, rewired_edges, item, proj_list, project_scope
            )

        if evt:
            graph_analytics.refresh_tree_metadata(project_scope)
            evt["persona_id"] = persona_id
            evt["persona_name"] = dept_name
            evt["reorg_strategy"] = "wrapper" if _is_genesis(target_node) else "lateral"
        return evt

    def _apply_wrapper_split(
        self,
        target_node: GraphNode,
        sub_concepts: List[Dict],
        rewired_edges: List[Dict],
        item: Dict,
        proj_list: List[str],
        project_scope: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        concept_id = target_node.id
        sub_alias_map: Dict[str, str] = {}
        for sub in sub_concepts:
            new_sub_id = f"concept_{uuid.uuid4().hex[:8]}"
            alias = sub.get("sub_id_alias")
            if alias:
                sub_alias_map[alias] = new_sub_id
            sub_node = GraphNode(
                _id=new_sub_id,
                node_type="CONCEPT",
                title=sub.get("title", "Split Sub-Concept"),
                description=sub.get("description", ""),
                passage_ids=sub.get("passage_ids", target_node.passage_ids),
                project_ids=proj_list,
                metadata={"immutable": False, "split_under_genesis": concept_id},
            )
            self.db.upsert_node(sub_node)
            self.db.upsert_edge(
                GraphEdge(
                    _id=f"edge_{uuid.uuid4().hex[:8]}",
                    source_id=new_sub_id,
                    target_id=concept_id,
                    description="SUBSET_OF",
                    project_ids=proj_list,
                )
            )

        current_edges = self.db.get_edges(project_scope)
        deleted_neighbors = self._rewire_neighbors(
            concept_id, rewired_edges, sub_alias_map, current_edges, proj_list
        )

        new_title = item.get("parent_title") or item.get("hub_title")
        if new_title and not _is_genesis(target_node):
            target_node.title = new_title.strip()
        new_desc = item.get("parent_description") or item.get("hub_description")
        if new_desc:
            target_node.description = new_desc.strip()
        target_node.updated_at = time.time()
        self.db.upsert_node(target_node)

        return {
            "event": "reorg_completed",
            "node_id": concept_id,
            "node_title": target_node.title,
            "message": (
                f"Genesis wrapper split: {len(sub_concepts)} intermediate concept(s), "
                f"{len(deleted_neighbors)} neighbors rewired."
            ),
            "timestamp": time.time(),
        }

    def _apply_lateral_split(
        self,
        target_node: GraphNode,
        sub_concepts: List[Dict],
        rewired_edges: List[Dict],
        item: Dict,
        proj_list: List[str],
        project_scope: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        tree = MutableTreeIndex(project_id=project_scope)
        parent_id = tree.parent_of(target_node.id)
        if not parent_id:
            return self._apply_wrapper_split(
                target_node, sub_concepts, rewired_edges, item, proj_list, project_scope
            )

        sub_alias_map: Dict[str, str] = {}
        if sub_concepts:
            first = sub_concepts[0]
            sub_alias_map[first.get("sub_id_alias", "sub_1")] = target_node.id
            parent_title = item.get("parent_title") or item.get("hub_title")
            parent_desc = item.get("parent_description") or item.get("hub_description")
            if parent_title and not _is_genesis(target_node):
                target_node.title = parent_title.strip()
            else:
                target_node.title = first.get("title", target_node.title)
            if parent_desc:
                target_node.description = parent_desc.strip()
            else:
                target_node.description = first.get(
                    "description", target_node.description
                )
            target_node.updated_at = time.time()
            self.db.upsert_node(target_node)

        for sub in sub_concepts[1:]:
            new_id = f"concept_{uuid.uuid4().hex[:8]}"
            alias = sub.get("sub_id_alias")
            if alias:
                sub_alias_map[alias] = new_id
            sibling = GraphNode(
                _id=new_id,
                node_type="CONCEPT",
                title=sub.get("title", "Sibling Concept"),
                description=sub.get("description", ""),
                project_ids=proj_list,
                metadata={"immutable": False, "lateral_split_of": target_node.id},
            )
            self.db.upsert_node(sibling)
            self.db.upsert_edge(
                GraphEdge(
                    _id=f"edge_{uuid.uuid4().hex[:8]}",
                    source_id=new_id,
                    target_id=parent_id,
                    description="SUBSET_OF",
                    project_ids=proj_list,
                )
            )

        old_parent_edge_removed = False
        current_edges = self.db.get_edges(project_scope)
        for e in list(current_edges):
            if (
                e.source_id == target_node.id
                and e.target_id == parent_id
                and _is_subset_edge(e)
            ):
                self.db.delete_edge(e.id)
                old_parent_edge_removed = True
        if old_parent_edge_removed or sub_concepts:
            self.db.upsert_edge(
                GraphEdge(
                    _id=f"edge_{uuid.uuid4().hex[:8]}",
                    source_id=target_node.id,
                    target_id=parent_id,
                    description="SUBSET_OF",
                    project_ids=proj_list,
                )
            )

        deleted = self._rewire_neighbors_lateral(
            split_target_id=target_node.id,
            parent_id=parent_id,
            rewired_edges=rewired_edges,
            sub_alias_map=sub_alias_map,
            current_edges=self.db.get_edges(project_scope),
            proj_list=proj_list,
        )

        return {
            "event": "reorg_completed",
            "node_id": target_node.id,
            "node_title": target_node.title,
            "message": (
                f"Lateral split under parent '{parent_id}': "
                f"{len(sub_concepts)} sibling concept(s), {len(deleted)} neighbors rewired."
            ),
            "timestamp": time.time(),
        }

    def _rewire_neighbors(
        self,
        split_target_id: str,
        rewired_edges: List[Dict],
        sub_alias_map: Dict[str, str],
        current_edges: List[GraphEdge],
        proj_list: List[str],
    ) -> Set[str]:
        deleted_neighbors: Set[str] = set()
        for rewired in rewired_edges:
            neighbor_id = rewired.get("neighbor_id")
            sub_alias = rewired.get("connect_to_sub_alias")
            target_sub_id = sub_alias_map.get(sub_alias)
            if not (neighbor_id and target_sub_id):
                continue
            if neighbor_id not in deleted_neighbors:
                for old_edge in current_edges:
                    if (
                        old_edge.source_id == neighbor_id
                        and old_edge.target_id == split_target_id
                    ) or (
                        old_edge.source_id == split_target_id
                        and old_edge.target_id == neighbor_id
                    ):
                        self.db.delete_edge(old_edge.id)
                deleted_neighbors.add(neighbor_id)
            self.db.upsert_edge(
                GraphEdge(
                    _id=f"edge_{uuid.uuid4().hex[:8]}",
                    source_id=neighbor_id,
                    target_id=target_sub_id,
                    description=rewired.get("relation_type", "RELEVANT_TO"),
                    project_ids=proj_list,
                    metadata={"link_class": rewired.get("link_class", "clustered")},
                )
            )
        return deleted_neighbors

    def _rewire_neighbors_lateral(
        self,
        split_target_id: str,
        parent_id: str,
        rewired_edges: List[Dict],
        sub_alias_map: Dict[str, str],
        current_edges: List[GraphEdge],
        proj_list: List[str],
    ) -> Set[str]:
        deleted_neighbors: Set[str] = set()
        for rewired in rewired_edges:
            neighbor_id = rewired.get("neighbor_id")
            sub_alias = (rewired.get("connect_to_sub_alias") or "").upper()
            if not neighbor_id:
                continue
            if neighbor_id not in deleted_neighbors:
                for old_edge in list(current_edges):
                    if (
                        old_edge.source_id == neighbor_id
                        and old_edge.target_id == split_target_id
                    ) or (
                        old_edge.source_id == split_target_id
                        and old_edge.target_id == neighbor_id
                    ):
                        self.db.delete_edge(old_edge.id)
                deleted_neighbors.add(neighbor_id)

            if sub_alias in ("UNCLUSTERED", "MISC", "PARENT"):
                self.db.upsert_edge(
                    GraphEdge(
                        _id=f"edge_{uuid.uuid4().hex[:8]}",
                        source_id=neighbor_id,
                        target_id=parent_id,
                        description=rewired.get("relation_type", "RELEVANT_TO"),
                        project_ids=proj_list,
                        metadata={"link_class": "miscellaneous"},
                    )
                )
                continue

            target_id = sub_alias_map.get(rewired.get("connect_to_sub_alias"))
            if target_id:
                self.db.upsert_edge(
                    GraphEdge(
                        _id=f"edge_{uuid.uuid4().hex[:8]}",
                        source_id=neighbor_id,
                        target_id=target_id,
                        description=rewired.get("relation_type", "RELEVANT_TO"),
                        project_ids=proj_list,
                        metadata={"link_class": rewired.get("link_class", "clustered")},
                    )
                )
        return deleted_neighbors


def _is_subset_edge(edge: GraphEdge) -> bool:
    desc = (edge.description or "").upper()
    return "SUBSET_OF" in desc


graph_ingestion_engine = GraphIngestionEngine()

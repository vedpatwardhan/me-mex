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
from app.services.reorg_rewire_utils import (
    finalize_rewire_edges,
    is_overflow_rewire_alias,
    resolve_rewire_relation_type,
    sub_aliases_with_assigned_neighbors,
)


def _is_genesis(node: GraphNode) -> bool:
    return bool(
        node.metadata.get("is_genesis") or node.title.strip().lower() == "everything"
    )


def _ancestor_aliases(sub_alias: str) -> bool:
    return is_overflow_rewire_alias(sub_alias)


def _rewire_target_kind(
    raw_alias: str,
    *,
    is_genesis_split: bool,
    used_overflow_fallback: bool,
) -> str:
    """Classify where a neighbor landed after reorg commit."""
    alias_upper = (raw_alias or "").upper()
    if alias_upper == "EVERYTHING" or (is_genesis_split and used_overflow_fallback):
        return "genesis_everything"
    if alias_upper in ("ANCESTOR", "UNCLUSTERED", "MISC", "PARENT") or (
        not is_genesis_split and used_overflow_fallback
    ):
        return "ancestor"
    return "sub_concept"


def _rewire_target_label(kind: str, target_node: Optional[GraphNode]) -> str:
    if kind == "genesis_everything":
        return "Everything (Genesis)"
    if kind == "ancestor":
        title = target_node.title if target_node else "ancestor"
        return f"ancestor '{title}'"
    title = target_node.title if target_node else "sub-concept"
    return f"sub-concept '{title}'"


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

        edge_id = f"edge_{uuid.uuid4().hex[:8]}"
        edge_obj = GraphEdge(
            _id=edge_id,
            source_id=src_id,
            target_id=tgt_id,
            description=edge_data.get("description", "RELEVANT_TO"),
            project_ids=proj_list,
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
        rewired_edges = list(item.get("rewired_edges", []))
        if not sub_concepts:
            return None

        project_scope = proj_list[0] if proj_list else None
        rewired_edges = finalize_rewire_edges(
            concept_id,
            project_scope,
            rewired_edges,
            is_genesis_split=_is_genesis(target_node),
            explicit_neighbor_ids=item.get("partition_neighbor_ids"),
        )
        ungrouped = 0
        if _is_genesis(target_node):
            evt = self._apply_wrapper_split(
                target_node, sub_concepts, rewired_edges, item, proj_list, project_scope
            )
            strategy = "wrapper"
        else:
            evt, ungrouped = self._apply_lateral_split(
                target_node, sub_concepts, rewired_edges, item, proj_list, project_scope
            )
            strategy = "replacement"

        if evt:
            graph_analytics.refresh_tree_metadata(project_scope)
            evt["persona_id"] = persona_id
            evt["persona_name"] = dept_name
            evt["reorg_strategy"] = strategy
            evt["ungrouped_to_ancestor_count"] = ungrouped
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
        used_aliases = sub_aliases_with_assigned_neighbors(rewired_edges)
        sub_concepts_to_mint = [
            sub for sub in sub_concepts if sub.get("sub_id_alias") in used_aliases
        ]
        sub_alias_map: Dict[str, str] = {}
        for sub in sub_concepts_to_mint:
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
        deleted_neighbors, ungrouped, rewire_events = self._rewire_neighbors(
            split_target_id=concept_id,
            split_hub_title=target_node.title,
            fallback_target_id=concept_id,
            rewired_edges=rewired_edges,
            sub_alias_map=sub_alias_map,
            current_edges=current_edges,
            proj_list=proj_list,
            is_genesis_split=True,
        )

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
                f"Genesis wrapper split: {len(sub_alias_map)} intermediate concept(s) minted, "
                f"{len(deleted_neighbors)} neighbors rewired, {ungrouped} left on Everything."
            ),
            "rewire_events": rewire_events,
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
    ) -> tuple[Optional[Dict[str, Any]], int]:
        tree = MutableTreeIndex(project_id=project_scope)
        parent_id = tree.parent_of(target_node.id)
        if not parent_id:
            evt = self._apply_wrapper_split(
                target_node, sub_concepts, rewired_edges, item, proj_list, project_scope
            )
            return evt, 0

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

        current_edges = self.db.get_edges(project_scope)
        for e in list(current_edges):
            if (
                e.source_id == target_node.id
                and e.target_id == parent_id
                and _is_subset_edge(e)
            ):
                self.db.delete_edge(e.id)
        self.db.upsert_edge(
            GraphEdge(
                _id=f"edge_{uuid.uuid4().hex[:8]}",
                source_id=target_node.id,
                target_id=parent_id,
                description="SUBSET_OF",
                project_ids=proj_list,
            )
        )

        deleted, ungrouped, rewire_events = self._rewire_neighbors(
            split_target_id=target_node.id,
            split_hub_title=target_node.title,
            fallback_target_id=parent_id,
            rewired_edges=rewired_edges,
            sub_alias_map=sub_alias_map,
            current_edges=self.db.get_edges(project_scope),
            proj_list=proj_list,
            is_genesis_split=False,
        )

        evt = {
            "event": "reorg_completed",
            "node_id": target_node.id,
            "node_title": target_node.title,
            "parent_id": parent_id,
            "message": (
                f"Replacement split under parent '{parent_id}': "
                f"{len(sub_concepts)} sibling concept(s), {len(deleted)} rewired, "
                f"{ungrouped} promoted to ancestor."
            ),
            "rewire_events": rewire_events,
            "timestamp": time.time(),
        }
        return evt, ungrouped

    def _rewire_neighbors(
        self,
        split_target_id: str,
        split_hub_title: str,
        fallback_target_id: str,
        rewired_edges: List[Dict],
        sub_alias_map: Dict[str, str],
        current_edges: List[GraphEdge],
        proj_list: List[str],
        is_genesis_split: bool,
    ) -> tuple[Set[str], int, List[Dict[str, Any]]]:
        deleted_neighbors: Set[str] = set()
        ungrouped_count = 0
        rewire_events: List[Dict[str, Any]] = []
        ts = time.time()
        for rewired in rewired_edges:
            neighbor_id = rewired.get("neighbor_id")
            raw_alias = rewired.get("connect_to_sub_alias") or ""
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

            used_overflow_fallback = False
            if _ancestor_aliases(raw_alias):
                target_id = fallback_target_id
                ungrouped_count += 1
                used_overflow_fallback = True
            else:
                target_id = sub_alias_map.get(raw_alias)
            if not target_id:
                target_id = fallback_target_id
                ungrouped_count += 1
                used_overflow_fallback = True

            relation = resolve_rewire_relation_type(
                neighbor_id,
                split_target_id,
                current_edges,
                rewired.get("relation_type"),
            )
            self.db.upsert_edge(
                GraphEdge(
                    _id=f"edge_{uuid.uuid4().hex[:8]}",
                    source_id=neighbor_id,
                    target_id=target_id,
                    description=relation,
                    project_ids=proj_list,
                )
            )

            neighbor_node = self.db.get_node(neighbor_id)
            target_node = self.db.get_node(target_id)
            target_kind = _rewire_target_kind(
                raw_alias,
                is_genesis_split=is_genesis_split,
                used_overflow_fallback=used_overflow_fallback,
            )
            target_label = _rewire_target_label(target_kind, target_node)
            neighbor_title = neighbor_node.title if neighbor_node else neighbor_id
            rewire_events.append(
                {
                    "event": "reorg_neighbor_rewired",
                    "split_hub_id": split_target_id,
                    "split_hub_title": split_hub_title,
                    "source_id": neighbor_id,
                    "source_title": neighbor_title,
                    "target_id": target_id,
                    "target_title": target_node.title if target_node else target_id,
                    "target_kind": target_kind,
                    "connect_to_sub_alias": raw_alias,
                    "relation_type": relation,
                    "description": rewired.get("description") or "",
                    "message": (
                        f"Re-wired '{neighbor_title}' → {target_label} ({relation})."
                    ),
                    "timestamp": ts,
                }
            )
        return deleted_neighbors, ungrouped_count, rewire_events


def _is_subset_edge(edge: GraphEdge) -> bool:
    desc = (edge.description or "").upper()
    return "SUBSET_OF" in desc


graph_ingestion_engine = GraphIngestionEngine()

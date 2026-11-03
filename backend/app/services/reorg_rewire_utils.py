"""Shared reorg rewire closure and hub neighbor discovery (scratchpad v0.2.2)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from app.db import db_engine
from app.models import GraphEdge
from app.services.graph_analytics import MutableTreeIndex


def _is_subset_edge(edge: GraphEdge) -> bool:
    desc = (edge.description or "").upper()
    return "SUBSET_OF" in desc or "SUBSET" in desc


def _skip_tree_parent_backbone(
    split_target_id: str, nb_id: str, edge: GraphEdge, project_scope: Optional[str]
) -> bool:
    """SUBSET_OF link to tree parent is structural, not a partition neighbor."""
    tree = MutableTreeIndex(project_id=project_scope)
    parent_id = tree.parent_of(split_target_id)
    if not parent_id or nb_id != parent_id:
        return False
    return _is_subset_edge(edge)


def hub_neighbor_relations(
    split_target_id: str, project_scope: Optional[str]
) -> Dict[str, str]:
    """Map neighbor_id -> relation description for non-ROOT nodes adjacent to split_target."""
    relations: Dict[str, str] = {}
    for e in db_engine.get_edges(project_scope):
        nb_id: Optional[str] = None
        if e.source_id == split_target_id:
            nb_id = e.target_id
        elif e.target_id == split_target_id:
            nb_id = e.source_id
        else:
            continue
        if not nb_id or nb_id in relations:
            continue
        if _skip_tree_parent_backbone(split_target_id, nb_id, e, project_scope):
            continue
        nb = db_engine.get_node(nb_id)
        if not nb or nb.is_root_node:
            continue
        relations[nb_id] = e.description or "RELEVANT_TO"
    return relations


def finalize_rewire_edges(
    split_target_id: str,
    project_scope: Optional[str],
    rewired_edges: List[Dict[str, Any]],
    *,
    is_genesis_split: bool,
    explicit_neighbor_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Ensure every hub neighbor in scope appears once in rewired_edges.
    Missing neighbors orphan to ANCESTOR (non-Genesis) or EVERYTHING (Genesis).
    """
    expected: Set[str]
    if explicit_neighbor_ids is not None:
        expected = set(explicit_neighbor_ids)
    else:
        expected = set(hub_neighbor_relations(split_target_id, project_scope).keys())

    result: List[Dict[str, Any]] = list(rewired_edges)
    covered = {r.get("neighbor_id") for r in result if r.get("neighbor_id")}

    orphan_alias = "EVERYTHING" if is_genesis_split else "ANCESTOR"
    relations = hub_neighbor_relations(split_target_id, project_scope)
    for nid in expected:
        if nid in covered:
            continue
        result.append(
            {
                "neighbor_id": nid,
                "connect_to_sub_alias": orphan_alias,
                "relation_type": relations.get(nid, "RELEVANT_TO"),
                "description": "Closure default orphan promotion.",
            }
        )
        covered.add(nid)

    return result


def resolve_rewire_relation_type(
    neighbor_id: str,
    split_target_id: str,
    current_edges: List[GraphEdge],
    llm_relation: Optional[str],
) -> str:
    """Preserve SUBSET_OF for mutable tree children when reparenting under a split."""
    nb = db_engine.get_node(neighbor_id)
    for old in current_edges:
        if old.source_id == neighbor_id and old.target_id == split_target_id:
            if _is_subset_edge(old) and nb and not nb.is_immutable:
                return "SUBSET_OF"
            return (llm_relation or old.description or "RELEVANT_TO").strip()
        if old.source_id == split_target_id and old.target_id == neighbor_id:
            if _is_subset_edge(old) and nb and not nb.is_immutable:
                return "SUBSET_OF"
            return (llm_relation or old.description or "RELEVANT_TO").strip()
    return (llm_relation or "RELEVANT_TO").strip()

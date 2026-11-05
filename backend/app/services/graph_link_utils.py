"""Uniform graph edges and metadata-backed mutable tree parent links."""

from __future__ import annotations

import uuid
from typing import List, Optional

from app.db import db_engine
from app.models import GraphEdge, GraphNode

MUTABLE_PARENT_META_KEY = "mutable_parent_id"


def legacy_infer_mutable_parent_id(
    child_id: str,
    edges: List[GraphEdge],
    node_map: dict[str, GraphNode],
) -> Optional[str]:
    """One-time migration: infer parent from pre-unification edge descriptions."""
    child = node_map.get(child_id)
    if not child or child.is_immutable:
        return None
    for e in edges:
        desc = (e.description or "").upper()
        if "SUBSET" not in desc:
            continue
        if e.source_id != child_id:
            continue
        parent = node_map.get(e.target_id)
        if parent and not parent.is_immutable:
            return e.target_id
    return None


def migrate_legacy_mutable_parent_metadata(project_id: Optional[str]) -> None:
    """Persist mutable_parent_id from legacy edges when metadata is missing."""
    nodes = db_engine.get_nodes(project_id)
    edges = db_engine.get_edges(project_id)
    node_map = {n.id: n for n in nodes}
    for n in nodes:
        if n.is_immutable or n.is_root_node:
            continue
        if n.metadata.get(MUTABLE_PARENT_META_KEY):
            continue
        parent_id = legacy_infer_mutable_parent_id(n.id, edges, node_map)
        if not parent_id:
            continue
        meta = dict(n.metadata)
        meta[MUTABLE_PARENT_META_KEY] = parent_id
        n.metadata = meta
        db_engine.upsert_node(n)


def delete_edges_between(
    a_id: str,
    b_id: str,
    project_scope: Optional[str],
) -> None:
    for e in list(db_engine.get_edges(project_scope)):
        if (e.source_id == a_id and e.target_id == b_id) or (
            e.source_id == b_id and e.target_id == a_id
        ):
            db_engine.delete_edge(e.id)


def link_nodes(
    source_id: str,
    target_id: str,
    project_ids: List[str],
    description: str = "",
    project_scope: Optional[str] = None,
) -> GraphEdge:
    """Create an undifferentiated edge (optional natural-language description only)."""
    for existing in db_engine.get_edges(project_scope):
        if (existing.source_id == source_id and existing.target_id == target_id) or (
            existing.source_id == target_id and existing.target_id == source_id
        ):
            return existing
    edge = GraphEdge(
        _id=f"edge_{uuid.uuid4().hex[:8]}",
        source_id=source_id,
        target_id=target_id,
        description=(description or "").strip(),
        project_ids=project_ids,
    )
    db_engine.upsert_edge(edge)
    return edge


def set_mutable_parent(
    child_id: str,
    parent_id: str,
    project_ids: List[str],
    project_scope: Optional[str] = None,
) -> None:
    """Record tree parent on the child node and ensure a single child→parent graph edge."""
    child = db_engine.get_node(child_id)
    if not child:
        return
    old_parent = child.metadata.get(MUTABLE_PARENT_META_KEY)
    meta = dict(child.metadata)
    meta[MUTABLE_PARENT_META_KEY] = parent_id
    child.metadata = meta
    db_engine.upsert_node(child)

    if old_parent and old_parent != parent_id:
        delete_edges_between(child_id, old_parent, project_scope)
    delete_edges_between(child_id, parent_id, project_scope)
    link_nodes(
        child_id, parent_id, project_ids, description="", project_scope=project_scope
    )

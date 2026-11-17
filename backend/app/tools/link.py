from __future__ import annotations

from app.db import ToolContext
from app.models import NodeKind, V2Edge, new_id

ROOT_LINK_KINDS = {NodeKind.ROOT}
INSIGHT_TARGETS = {NodeKind.INSIGHT, NodeKind.CONCEPT_M}


def create_root_insight_edges(
    ctx: ToolContext,
    *,
    root_id: str,
    target_ids: list[str],
    note: str = "",
) -> dict:
    root = ctx.store.get_node(root_id)
    if root.node_kind != NodeKind.ROOT:
        raise ValueError("create_root_insight_edges requires ROOT source")
    edge_ids: list[str] = []
    for tid in target_ids:
        target = ctx.store.get_node(tid)
        if target.node_kind == NodeKind.CONCEPT_I:
            raise ValueError("default: link ROOT to hubs/insights, not CONCEPT_I")
        eid = new_id("edge")
        ctx.store.add_edge(
            V2Edge(
                _id=eid,
                source_id=root_id,
                target_id=tid,
                note=note,
                project_id=ctx.project_id,
            )
        )
        edge_ids.append(eid)
    return {"edge_ids": edge_ids}


def highlight_nodes(ctx: ToolContext, *, node_ids: list[str]) -> dict:
    ctx.store.set_highlight_ids(ctx.thread_id, node_ids)
    return {"highlighted": node_ids}


def search_nodes_keyword(ctx: ToolContext, *, query: str, limit: int = 20) -> dict:
    nodes = ctx.store.list_nodes(ctx.project_id)
    q = query.lower()
    hits = [
        {"id": n.id, "title": n.title, "node_kind": n.node_kind.value}
        for n in nodes
        if q in n.title.lower() or q in n.description.lower()
    ][:limit]
    return {"results": hits}


def query_nodes_by_embedding(
    ctx: ToolContext,
    *,
    query_vector: list[float],
    limit: int = 10,
) -> dict:
    """Deterministic stub: rank by title length unless vectors stored later."""
    nodes = ctx.store.list_nodes(ctx.project_id)
    scored = sorted(nodes, key=lambda n: len(n.title), reverse=True)[:limit]
    return {
        "results": [{"id": n.id, "title": n.title} for n in scored],
        "query_vector_dim": len(query_vector),
    }

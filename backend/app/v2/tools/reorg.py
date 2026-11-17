from __future__ import annotations

from typing import Any

from app.v2.db import ToolContext
from app.v2.models import NodeKind, V2Edge, new_id


def write_reorg_proposal(ctx: ToolContext, *, proposal: dict[str, Any]) -> dict:
    key = new_id("reorg_prop")
    ctx.store._db.reorg_proposals.replace_one(
        {"_id": key},
        {"_id": key, "project_id": ctx.project_id, **proposal},
        upsert=True,
    )
    return {"proposal_id": key}


def preview_reorg_diff(ctx: ToolContext, *, proposal_id: str) -> dict:
    doc = ctx.store._db.reorg_proposals.find_one({"_id": proposal_id})
    if not doc:
        raise ValueError("proposal not found")
    return {
        "before": doc.get("before", {}),
        "after": doc.get("after", {}),
        "proposal_id": proposal_id,
    }


def apply_reorg_plan(ctx: ToolContext, *, proposal_id: str) -> dict:
    doc = ctx.store._db.reorg_proposals.find_one({"_id": proposal_id})
    if not doc:
        raise ValueError("proposal not found")
    moves = doc.get("moves", [])
    for move in moves:
        relocate_under_parent(
            ctx, node_id=move["node_id"], new_parent_id=move["parent_id"]
        )
    return {"proposal_id": proposal_id, "moved": len(moves)}


def split_section(ctx: ToolContext, *, hub_id: str, new_hub_title: str) -> dict:
    hub = ctx.store.assert_mutable(hub_id)
    new_id_hub = new_id("hub")
    from app.v2.models import V2Node

    child = V2Node(
        _id=new_id_hub,
        title=new_hub_title,
        description="",
        node_kind=NodeKind.CONCEPT_M,
        project_id=ctx.project_id,
    )
    ctx.store.upsert_node(child)
    ctx.store.add_edge(
        V2Edge(
            _id=new_id("edge"),
            source_id=hub_id,
            target_id=new_id_hub,
            project_id=ctx.project_id,
        )
    )
    return {"new_hub_id": new_id_hub}


def merge_mutable_nodes(ctx: ToolContext, *, source_id: str, target_id: str) -> dict:
    ctx.store.assert_mutable(source_id)
    ctx.store.assert_mutable(target_id)
    for nid in ctx.store.neighbors(source_id):
        eid = new_id("edge")
        ctx.store.add_edge(
            V2Edge(
                _id=eid, source_id=target_id, target_id=nid, project_id=ctx.project_id
            )
        )
    ctx.store.delete_node(source_id, force=True)
    return {"merged_into": target_id}


def relocate_under_parent(
    ctx: ToolContext, *, node_id: str, new_parent_id: str
) -> dict:
    ctx.store.assert_mutable(node_id)
    eid = new_id("edge")
    ctx.store.add_edge(
        V2Edge(
            _id=eid,
            source_id=new_parent_id,
            target_id=node_id,
            project_id=ctx.project_id,
        )
    )
    return {"node_id": node_id, "parent_id": new_parent_id}


def add_edge(
    ctx: ToolContext, *, source_id: str, target_id: str, note: str = ""
) -> dict:
    eid = new_id("edge")
    ctx.store.add_edge(
        V2Edge(
            _id=eid,
            source_id=source_id,
            target_id=target_id,
            note=note,
            project_id=ctx.project_id,
        )
    )
    return {"edge_id": eid}


def remove_edge(ctx: ToolContext, *, edge_id: str) -> dict:
    ctx.store.remove_edge(edge_id)
    return {"edge_id": edge_id}


def update_edge_note(ctx: ToolContext, *, edge_id: str, note: str) -> dict:
    doc = ctx.store._db.edges.find_one({"_id": edge_id})
    if not doc:
        raise ValueError("edge not found")
    ctx.store._db.edges.update_one(
        {"_id": edge_id}, {"$set": {"note": note, "description": note}}
    )
    return {"edge_id": edge_id}


def edit_mutable_node(
    ctx: ToolContext,
    *,
    node_id: str,
    title: str | None = None,
    description: str | None = None,
) -> dict:
    node = ctx.store.assert_mutable(node_id)
    if title is not None:
        node.title = title
    if description is not None:
        node.description = description
    ctx.store.upsert_node(node)
    return {"node_id": node_id}


def rename_node(ctx: ToolContext, *, node_id: str, title: str) -> dict:
    return edit_mutable_node(ctx, node_id=node_id, title=title)


def set_todo_status(ctx: ToolContext, *, node_id: str, status: str) -> dict:
    node = ctx.store.get_node(node_id)
    if node.node_kind != NodeKind.TODO:
        raise ValueError("not a TODO")
    node.metadata["status"] = status
    ctx.store.upsert_node(node)
    return {"node_id": node_id, "status": status}


def delete_node(ctx: ToolContext, *, node_id: str) -> dict:
    ctx.store.delete_node(node_id)
    return {"node_id": node_id}


def archive_node(ctx: ToolContext, *, node_id: str) -> dict:
    node = ctx.store.get_node(node_id)
    node.metadata["archived"] = True
    ctx.store.upsert_node(node)
    return {"node_id": node_id}

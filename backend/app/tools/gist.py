from __future__ import annotations

from app.db import ToolContext
from app.models import NodeKind, Node, new_id


def create_or_update_root_gist(
    ctx: ToolContext,
    *,
    title: str,
    gist: str,
    root_id: str | None = None,
) -> dict:
    store = ctx.store
    rid = root_id or new_id("root")
    node = Node(
        _id=rid,
        title=title,
        description=gist,
        node_kind=NodeKind.ROOT,
        project_id=ctx.project_id,
    )
    store.upsert_node(node)
    return {"root_id": rid, "title": title, "gist": gist}


def attach_source_uri(ctx: ToolContext, *, root_id: str, uri: str) -> dict:
    node = ctx.store.get_node(root_id)
    if node.node_kind != NodeKind.ROOT:
        raise ValueError("attach_source_uri requires ROOT")
    node.source_uri = uri
    node.metadata["source_uri"] = uri
    ctx.store.upsert_node(node)
    return {"root_id": root_id, "source_uri": uri}


def create_note(ctx: ToolContext, *, title: str, body: str) -> dict:
    nid = new_id("note")
    node = Node(
        _id=nid,
        title=title,
        description=body,
        node_kind=NodeKind.NOTE,
        project_id=ctx.project_id,
    )
    ctx.store.upsert_node(node)
    return {"node_id": nid}


def create_todo(ctx: ToolContext, *, title: str, body: str = "") -> dict:
    nid = new_id("todo")
    node = Node(
        _id=nid,
        title=title,
        description=body,
        node_kind=NodeKind.TODO,
        project_id=ctx.project_id,
        metadata={"status": "open"},
    )
    ctx.store.upsert_node(node)
    return {"node_id": nid}


def promote_todo_to_concept_m(ctx: ToolContext, *, todo_id: str) -> dict:
    node = ctx.store.get_node(todo_id)
    if node.node_kind != NodeKind.TODO:
        raise ValueError("promote_todo requires TODO")
    node.node_kind = NodeKind.CONCEPT_M
    node.metadata.pop("status", None)
    ctx.store.upsert_node(node)
    return {"node_id": todo_id, "node_kind": NodeKind.CONCEPT_M.value}

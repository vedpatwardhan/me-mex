from __future__ import annotations

import hashlib
import time

from app.v2.db import ToolContext
from app.v2.models import NodeKind, StagingBundle, StagingConcept, V2Node, new_id
from app.v2.tools import fetch as fetch_tool


def _staging_key(root_id: str | None, url: str | None) -> str:
    if root_id:
        return f"staging_root_{root_id}"
    return f"staging_url_{hashlib.sha256((url or '').encode()).hexdigest()[:16]}"


def upsert_staging_bundle(
    ctx: ToolContext,
    *,
    root_id: str | None,
    pending_url: str | None,
    concepts: list[dict],
    content_hash: str = "",
) -> dict:
    bundle = StagingBundle(
        root_id=root_id,
        pending_url=pending_url,
        content_hash=content_hash,
        concepts=[StagingConcept(**c) for c in concepts],
        updated_at=time.time(),
    )
    key = _staging_key(root_id, pending_url)
    ctx.store.upsert_staging(key, bundle)
    return {"staging_key": key, "concept_count": len(bundle.concepts)}


def edit_staging_concept(
    ctx: ToolContext,
    *,
    staging_key: str,
    concept_id: str,
    title: str | None = None,
    description: str | None = None,
    dropped: bool | None = None,
) -> dict:
    bundle = ctx.store.get_staging(staging_key)
    for c in bundle.concepts:
        if c.concept_id == concept_id:
            if title is not None:
                c.title = title
            if description is not None:
                c.description = description
            if dropped is not None:
                c.dropped = dropped
            break
    else:
        raise ValueError(f"concept {concept_id} not in staging")
    ctx.store.upsert_staging(staging_key, bundle)
    return {"staging_key": staging_key}


def commit_intra_doc_graph(
    ctx: ToolContext,
    *,
    staging_key: str,
    root_id: str,
) -> dict:
    bundle = ctx.store.get_staging(staging_key)
    root = ctx.store.get_node(root_id)
    if root.node_kind != NodeKind.ROOT:
        raise ValueError("commit requires ROOT parent")
    created: list[str] = []
    for concept in bundle.concepts:
        if concept.dropped:
            continue
        cid = new_id("ci")
        passage_id = new_id("pass")
        ctx.store.upsert_passage(
            passage_id, root_id, concept.description or concept.title
        )
        node = V2Node(
            _id=cid,
            title=concept.title,
            description=concept.description,
            node_kind=NodeKind.CONCEPT_I,
            project_id=ctx.project_id,
            passage_ids=[passage_id],
            parent_root_id=root_id,
            metadata={"immutable": True, "parent_root_id": root_id},
        )
        ctx.store.upsert_node(node)
        from app.v2.models import V2Edge

        ctx.store.add_edge(
            V2Edge(
                _id=new_id("edge"),
                source_id=root_id,
                target_id=cid,
                project_id=ctx.project_id,
            )
        )
        created.append(cid)
    return {"root_id": root_id, "concept_ids": created}


def enqueue_staging_approval(ctx: ToolContext, staging_key: str) -> str:
    from app.v2.tools.dock import enqueue_pending_approval

    return enqueue_pending_approval(
        ctx,
        approval_type="intra_doc_staging",
        title="Review intra-doc staging",
        payload={"staging_key": staging_key},
    )

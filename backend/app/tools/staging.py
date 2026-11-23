from __future__ import annotations

import hashlib
import time

from app.db import ToolContext
from app.models import Node, NodeKind, StagingBundle, StagingConcept, StagingPassage, new_id
from app.services.timing import timed_tool


def _staging_key(root_id: str | None, url: str | None) -> str:
    if root_id:
        return f"staging_root_{root_id}"
    return f"staging_url_{hashlib.sha256((url or '').encode()).hexdigest()[:16]}"


@timed_tool
def upsert_staging_bundle(
    ctx: ToolContext,
    *,
    root_id: str | None,
    pending_url: str | None,
    concepts: list[dict],
    passages: list[dict] | None = None,
    source_title: str = "",
    doc_description: str = "",
    doc_type: str = "paper",
    content_hash: str = "",
) -> dict:
    bundle = StagingBundle(
        root_id=root_id,
        pending_url=pending_url,
        source_title=source_title,
        doc_description=doc_description,
        doc_type=doc_type,
        content_hash=content_hash,
        concepts=[StagingConcept(**c) for c in concepts],
        passages=[StagingPassage(**p) for p in (passages or [])],
        updated_at=time.time(),
    )
    key = _staging_key(root_id, pending_url)
    ctx.store.upsert_staging(key, bundle)
    return {
        "staging_key": key,
        "concept_count": len(bundle.concepts),
        "source_title": bundle.source_title,
        "source_url": bundle.pending_url,
        "doc_description": bundle.doc_description,
        "concepts": [concept.model_dump() for concept in bundle.concepts],
    }


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


@timed_tool
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
    passage_ids_by_index: dict[int, str] = {}
    for passage in bundle.passages:
        passage_id = new_id("pass")
        ctx.store.upsert_passage(
            passage_id,
            root_id,
            passage.text,
            index=passage.passage_index,
        )
        passage_ids_by_index[passage.passage_index] = passage_id
    created: list[str] = []
    for concept_index, concept in enumerate(bundle.concepts):
        if concept.dropped:
            continue
        cid = new_id("ci")
        passage_ids = [
            passage_ids_by_index[index]
            for index in concept.passage_indices
            if index in passage_ids_by_index
        ]
        if not bundle.passages:
            # Backward-compatible staging records predate source passage provenance.
            passage_id = new_id("pass")
            ctx.store.upsert_passage(
                passage_id,
                root_id,
                concept.description or concept.title,
                index=concept_index,
            )
            passage_ids = [passage_id]
        elif not passage_ids:
            raise ValueError(f"staged concept {concept.concept_id} has no source passages")
        node = Node(
            _id=cid,
            title=concept.title,
            description=concept.description,
            node_kind=NodeKind.CONCEPT_I,
            project_id=ctx.project_id,
            passage_ids=passage_ids,
            parent_root_id=root_id,
            metadata={"immutable": True, "parent_root_id": root_id},
        )
        ctx.store.upsert_node(node)
        from app.models import Edge

        ctx.store.add_edge(
            Edge(
                _id=new_id("edge"),
                source_id=root_id,
                target_id=cid,
                project_id=ctx.project_id,
            )
        )
        created.append(cid)
    return {"root_id": root_id, "concept_ids": created}


def enqueue_staging_approval(ctx: ToolContext, staging_key: str) -> str:
    from app.tools.dock import enqueue_pending_approval

    return enqueue_pending_approval(
        ctx,
        approval_type="intra_doc_staging",
        title="Review intra-doc staging",
        payload={"staging_key": staging_key},
    )

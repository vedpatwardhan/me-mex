from app.db import ToolContext
from app.models import NodeKind
from app.tools import dock, gist, staging


def test_staging_commit(store, project):
    ctx = ToolContext(project_id=project.id, thread_id="t1", store=store)
    root = gist.create_or_update_root_gist(ctx, title="R", gist="g")
    key = staging.upsert_staging_bundle(
        ctx,
        root_id=root["root_id"],
        pending_url=None,
        concepts=[{"concept_id": "c1", "title": "Claim", "description": "text"}],
    )
    out = staging.commit_intra_doc_graph(
        ctx, staging_key=key["staging_key"], root_id=root["root_id"]
    )
    assert len(out["concept_ids"]) == 1
    children = [n for n in store.list_nodes(project.id) if n.node_kind == NodeKind.CONCEPT_I]
    assert len(children) == 1


def test_url_only_deep_read_creates_root_and_commits_source_passages(store, project):
    from app.agents.graph import resume_approval

    ctx = ToolContext(project_id=project.id, thread_id="url-deep-read", store=store)
    source_url = "https://arxiv.org/pdf/2605.11550"
    staged = staging.upsert_staging_bundle(
        ctx,
        root_id=None,
        pending_url=source_url,
        source_title="Detailed Paper",
        doc_description="A grounded description of the paper.",
        concepts=[
            {
                "concept_id": "c1",
                "title": "Main method",
                "description": "The method combines both stages.",
                "passage_indices": [0, 1],
            }
        ],
        passages=[
            {"passage_index": 0, "text": "Original passage about the method."},
            {"passage_index": 1, "text": "Original passage about its evaluation."},
        ],
        content_hash="source-hash",
    )
    approval_id = dock.enqueue_pending_approval(
        ctx,
        approval_type="intra_doc_staging",
        title="Review intra-doc staging",
        payload=staged,
    )

    result = resume_approval(
        store=store,
        project_id=project.id,
        thread_id=ctx.thread_id,
        approval_id=approval_id,
        action="approve",
    )

    root_id = result["root_id"]
    root = store.get_node(root_id)
    concept = store.get_node(result["concept_ids"][0])
    source_passages = store.get_passages(concept.passage_ids)
    assert root.title == "Detailed Paper"
    assert root.description == "A grounded description of the paper."
    assert root.source_uri == source_url
    assert concept.parent_root_id == root_id
    assert {passage["text_content"] for passage in source_passages} == {
        "Original passage about the method.",
        "Original passage about its evaluation.",
    }
    assert {passage["chunk_index"] for passage in source_passages} == {0, 1}


def test_url_only_deep_read_reuses_existing_source_root(store, project):
    from app.agents.graph import resume_approval

    ctx = ToolContext(project_id=project.id, thread_id="existing-source-root", store=store)
    source_url = "https://arxiv.org/pdf/2605.11550"
    existing = gist.create_or_update_root_gist(
        ctx,
        title="Existing paper ROOT",
        gist="Existing gist.",
    )
    gist.attach_source_uri(ctx, root_id=existing["root_id"], uri=source_url)
    staged = staging.upsert_staging_bundle(
        ctx,
        root_id=None,
        pending_url=source_url,
        source_title="Fetched title",
        doc_description="Deep-read description.",
        concepts=[
            {
                "concept_id": "c1",
                "title": "Concept",
                "description": "Detailed concept.",
                "passage_indices": [0],
            }
        ],
        passages=[{"passage_index": 0, "text": "Original source passage."}],
    )
    approval_id = dock.enqueue_pending_approval(
        ctx,
        approval_type="intra_doc_staging",
        title="Review intra-doc staging",
        payload=staged,
    )

    result = resume_approval(
        store=store,
        project_id=project.id,
        thread_id=ctx.thread_id,
        approval_id=approval_id,
        action="approve",
    )

    roots = [node for node in store.list_nodes(project.id) if node.node_kind == NodeKind.ROOT]
    concept = store.get_node(result["concept_ids"][0])
    assert len(roots) == 1
    assert result["root_id"] == existing["root_id"]
    assert concept.parent_root_id == existing["root_id"]

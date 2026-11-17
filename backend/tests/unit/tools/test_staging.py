from app.v2.db import ToolContext
from app.v2.models import NodeKind
from app.v2.tools import gist, staging


def test_staging_commit(v2_store, v2_project):
    ctx = ToolContext(project_id=v2_project.id, thread_id="t1", store=v2_store)
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
    children = [
        n
        for n in v2_store.list_nodes(v2_project.id)
        if n.node_kind == NodeKind.CONCEPT_I
    ]
    assert len(children) == 1

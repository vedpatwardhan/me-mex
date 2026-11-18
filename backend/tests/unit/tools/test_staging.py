from app.db import ToolContext
from app.models import NodeKind
from app.tools import gist, staging


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

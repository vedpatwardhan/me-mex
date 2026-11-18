"""W12 — manual canvas delete via REST; graph shrinks; no silent agent rewiring."""

from app.db import ToolContext
from app.models import Node, NodeKind, new_id
from app.tools import gist, link


def test_w12_delete_node_via_api(client, store, project_scoped):
    pid = project_scoped.id
    ctx = ToolContext(project_id=pid, thread_id="w12", store=store)
    root = gist.create_or_update_root_gist(ctx, title="Paper", gist="g")
    hub = Node(
        _id=new_id("hub"),
        title="Hub",
        description="",
        node_kind=NodeKind.CONCEPT_M,
        project_id=pid,
    )
    store.upsert_node(hub)
    link.create_root_insight_edges(ctx, root_id=root["root_id"], target_ids=[hub.id])
    node_id = hub.id
    edge_q = {"project_ids": pid}
    before_edges = store._db.edges.count_documents(edge_q)
    assert before_edges >= 1
    r = client.delete(f"/api/graph/nodes/{node_id}", params={"project_id": pid})
    assert r.status_code == 200
    assert store._db.nodes.find_one({"_id": node_id}) is None
    after_edges = store._db.edges.count_documents(edge_q)
    assert after_edges == before_edges - 1

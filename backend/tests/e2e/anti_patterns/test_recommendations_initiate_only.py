from app.v2.db import ToolContext
from app.v2.models import NodeKind, V2Edge, V2Node, new_id
from app.v2.tools import gist


def test_link_turn_no_edges_until_resume(client, v2_store, v2_project_scoped):
    pid = v2_project_scoped.id
    ctx = ToolContext(project_id=pid, thread_id="x", store=v2_store)
    root = gist.create_or_update_root_gist(ctx, title="R", gist="g")
    hub = V2Node(
        _id=new_id("hub"),
        title="Insight hub",
        description="",
        node_kind=NodeKind.CONCEPT_M,
        project_id=pid,
    )
    v2_store.upsert_node(hub)
    before = v2_store._db.edges.count_documents({})
    r = client.post(
        "/api/v2/agent/turn",
        json={
            "text": "where does this paper connect?",
            "thread_id": "w4",
            "context_json": {
                "active_project_id": pid,
                "custom_fields": {"root_id": root["root_id"]},
            },
        },
    )
    assert r.json()["graph_write"] is False
    assert r.json()["details"]["approval_id"]
    after = v2_store._db.edges.count_documents({})
    assert after == before

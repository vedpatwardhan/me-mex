from app.db import ToolContext
from app.models import NodeKind, Edge, Node, new_id
from app.tools import gist


def test_link_turn_no_edges_until_resume(client, store, project_scoped):
    pid = project_scoped.id
    ctx = ToolContext(project_id=pid, thread_id="x", store=store)
    root = gist.create_or_update_root_gist(ctx, title="R", gist="g")
    hub = Node(
        _id=new_id("hub"),
        title="Insight hub",
        description="",
        node_kind=NodeKind.CONCEPT_M,
        project_id=pid,
    )
    store.upsert_node(hub)
    before = store._db.edges.count_documents({})
    r = client.post(
        "/api/agent/turn",
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
    after = store._db.edges.count_documents({})
    assert after == before

from app.v2.db import ToolContext
from app.v2.models import NodeKind, V2Node, new_id
from app.v2.tools import gist


def test_w4_approve_creates_edges(client, v2_store, v2_project_scoped):
    pid = v2_project_scoped.id
    ctx = ToolContext(project_id=pid, thread_id="x", store=v2_store)
    root = gist.create_or_update_root_gist(ctx, title="R", gist="g")
    hub = V2Node(
        _id=new_id("hub"),
        title="Hub",
        description="",
        node_kind=NodeKind.CONCEPT_M,
        project_id=pid,
    )
    v2_store.upsert_node(hub)
    r = client.post(
        "/api/v2/agent/turn",
        json={
            "text": "connect this ROOT",
            "thread_id": "w4b",
            "context_json": {
                "active_project_id": pid,
                "custom_fields": {"root_id": root["root_id"]},
            },
        },
    )
    aid = r.json()["details"]["approval_id"]
    client.post(
        "/api/v2/agent/resume",
        json={
            "thread_id": "w4b",
            "approval_id": aid,
            "action": "approve",
            "context_json": {"active_project_id": pid},
        },
    )
    neighbors = v2_store.neighbors(root["root_id"])
    assert hub.id in neighbors or len(neighbors) > 0

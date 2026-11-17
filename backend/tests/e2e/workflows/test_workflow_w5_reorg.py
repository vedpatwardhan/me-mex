from app.v2.db import ToolContext
from app.v2.models import NodeKind, V2Edge, V2Node, new_id


def _crowded_hub(v2_store, project_id: str) -> str:
    hub_id = new_id("hub")
    v2_store.upsert_node(
        V2Node(
            _id=hub_id,
            title="Crowded",
            description="",
            node_kind=NodeKind.CONCEPT_M,
            project_id=project_id,
        )
    )
    for i in range(9):
        nid = new_id("n")
        v2_store.upsert_node(
            V2Node(
                _id=nid,
                title=f"L{i}",
                description="",
                node_kind=NodeKind.NOTE,
                project_id=project_id,
            )
        )
        v2_store.add_edge(
            V2Edge(
                _id=new_id("e"), source_id=hub_id, target_id=nid, project_id=project_id
            )
        )
    return hub_id


def test_w5_reorg_preview_then_apply(client, v2_store, v2_project_scoped):
    pid = v2_project_scoped.id
    _crowded_hub(v2_store, pid)
    r = client.post(
        "/api/v2/agent/turn",
        json={
            "text": "split this crowded hub",
            "thread_id": "w5",
            "context_json": {"active_project_id": pid},
        },
    )
    assert r.json()["graph_write"] is False
    aid = r.json()["details"]["approval_id"]
    client.post(
        "/api/v2/agent/resume",
        json={
            "thread_id": "w5",
            "approval_id": aid,
            "action": "approve",
            "context_json": {"active_project_id": pid},
        },
    )

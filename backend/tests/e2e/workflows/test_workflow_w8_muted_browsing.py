"""W8 — muted session: no uplink text required; canvas context via custom_fields still routes."""

from app.models import Node, NodeKind, new_id


def test_w8_muted_turn_uses_custom_fields(client, store, project_scoped, mock_vllm_chat):
    pid = project_scoped.id
    hub = Node(
        _id=new_id("hub"),
        title="Hub",
        description="",
        node_kind=NodeKind.CONCEPT_M,
        project_id=pid,
    )
    store.upsert_node(hub)
    r = client.post(
        "/api/agent/turn",
        json={
            "text": "",
            "thread_id": "w8",
            "context_json": {
                "active_project_id": pid,
                "muted": True,
                "selected_node_ids": [hub.id],
                "custom_fields": {"intent": "summarize_selection"},
            },
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("reply")
    assert body.get("graph_write") is False

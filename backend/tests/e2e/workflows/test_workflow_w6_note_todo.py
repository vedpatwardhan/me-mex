from app.models import NodeKind


def test_w6_note_and_promote(client, v2_store, v2_project_scoped):
    pid = v2_project_scoped.id
    client.post(
        "/api/agent/turn",
        json={
            "text": "create todo: Read ERA paper",
            "thread_id": "w6",
            "context_json": {"active_project_id": pid},
        },
    )
    todos = [n for n in v2_store.list_nodes(pid) if n.node_kind == NodeKind.TODO]
    assert todos
    tid = todos[0].id
    r = client.post(
        "/api/agent/turn",
        json={
            "text": "promote todo",
            "thread_id": "w6b",
            "context_json": {
                "active_project_id": pid,
                "custom_fields": {"promote_todo_id": tid},
            },
        },
    )
    assert r.json()["graph_write"] is True
    assert v2_store.get_node(tid).node_kind == NodeKind.CONCEPT_M

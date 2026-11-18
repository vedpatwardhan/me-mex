from app.models import Edge, Node, NodeKind, new_id


def _crowded_hub(store, project_id: str) -> str:
    hub_id = new_id("hub")
    store.upsert_node(
        Node(
            _id=hub_id,
            title="Crowded",
            description="",
            node_kind=NodeKind.CONCEPT_M,
            project_id=project_id,
        )
    )
    for i in range(9):
        nid = new_id("n")
        store.upsert_node(
            Node(
                _id=nid,
                title=f"L{i}",
                description="",
                node_kind=NodeKind.NOTE,
                project_id=project_id,
            )
        )
        store.add_edge(
            Edge(_id=new_id("e"), source_id=hub_id, target_id=nid, project_id=project_id)
        )
    return hub_id


def test_w5_reorg_preview_then_apply(client, store, project_scoped):
    pid = project_scoped.id
    _crowded_hub(store, pid)
    r = client.post(
        "/api/agent/turn",
        json={
            "text": "split this crowded hub",
            "thread_id": "w5",
            "context_json": {"active_project_id": pid},
        },
    )
    assert r.json()["graph_write"] is False
    aid = r.json()["details"]["approval_id"]
    client.post(
        "/api/agent/resume",
        json={
            "thread_id": "w5",
            "approval_id": aid,
            "action": "approve",
            "context_json": {"active_project_id": pid},
        },
    )

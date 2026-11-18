from app.models import Edge, Node, NodeKind, new_id


def test_w11_retrieval_highlight(client, store, project_scoped):
    pid = project_scoped.id
    seed = Node(
        _id=new_id("seed"),
        title="Manipulation",
        description="",
        node_kind=NodeKind.CONCEPT_M,
        project_id=pid,
    )
    store.upsert_node(seed)
    leaf = Node(
        _id=new_id("leaf"),
        title="Policy",
        description="",
        node_kind=NodeKind.CONCEPT_M,
        project_id=pid,
    )
    store.upsert_node(leaf)
    store.add_edge(Edge(_id=new_id("e"), source_id=seed.id, target_id=leaf.id, project_id=pid))
    r = client.post(
        "/api/agent/turn",
        json={
            "text": "what relates to manipulation?",
            "thread_id": "w11",
            "context_json": {
                "active_project_id": pid,
                "custom_fields": {"query_node_id": seed.id},
            },
        },
    )
    assert r.json()["graph_write"] is False
    assert store.get_highlight_ids("w11")

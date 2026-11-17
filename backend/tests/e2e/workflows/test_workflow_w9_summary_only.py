def test_w9_summarize_no_graph_write(client, v2_store, v2_project_scoped):
    pid = v2_project_scoped.id
    before = len(v2_store.list_nodes(pid))
    r = client.post(
        "/api/agent/turn",
        json={
            "text": "summarize this thread",
            "thread_id": "w9",
            "context_json": {"active_project_id": pid},
        },
    )
    assert r.json()["graph_write"] is False
    assert len(v2_store.list_nodes(pid)) == before

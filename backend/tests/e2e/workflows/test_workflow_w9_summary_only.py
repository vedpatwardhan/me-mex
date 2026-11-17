def test_w9_summarize_no_graph_write(client, store, project_scoped):
    pid = project_scoped.id
    before = len(store.list_nodes(pid))
    r = client.post(
        "/api/agent/turn",
        json={
            "text": "summarize this thread",
            "thread_id": "w9",
            "context_json": {"active_project_id": pid},
        },
    )
    assert r.json()["graph_write"] is False
    assert len(store.list_nodes(pid)) == before

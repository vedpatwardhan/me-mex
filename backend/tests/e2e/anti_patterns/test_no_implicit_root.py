def test_gist_question_no_implicit_root(client, v2_store, v2_project):
    client.post(
        "/api/agent/turn",
        json={
            "text": "What's the gist?",
            "thread_id": "ap1",
            "context_json": {"active_project_id": v2_project.id},
        },
    )
    kinds = {n.node_kind.value for n in v2_store.list_nodes(v2_project.id)}
    assert "ROOT" not in kinds

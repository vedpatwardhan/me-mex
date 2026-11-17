def test_gist_question_no_implicit_root(client, store, project):
    client.post(
        "/api/agent/turn",
        json={
            "text": "What's the gist?",
            "thread_id": "ap1",
            "context_json": {"active_project_id": project.id},
        },
    )
    kinds = {n.node_kind.value for n in store.list_nodes(project.id)}
    assert "ROOT" not in kinds

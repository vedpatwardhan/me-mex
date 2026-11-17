def test_gist_inquiry_no_root(client, store, project):
    r = client.post(
        "/api/agent/turn",
        json={
            "text": "What's the gist of this paper?",
            "thread_id": "w2",
            "context_json": {"active_project_id": project.id},
        },
    )
    assert r.status_code == 200
    assert r.json()["graph_write"] is False
    roots = [n for n in store.list_nodes(project.id) if n.node_kind.value == "ROOT"]
    assert len(roots) == 0


def test_direct_gist_commit(client, store, project):
    r = client.post(
        "/api/agent/turn",
        json={
            "text": "create root",
            "thread_id": "w2b",
            "context_json": {
                "active_project_id": project.id,
                "custom_fields": {
                    "title": "ERA",
                    "gist": "Embodied rollout",
                    "force_gist_commit": True,
                },
            },
        },
    )
    assert r.status_code == 200
    assert r.json()["graph_write"] is True

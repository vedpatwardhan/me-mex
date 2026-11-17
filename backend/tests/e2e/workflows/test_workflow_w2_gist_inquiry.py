def test_gist_inquiry_no_root(client, v2_store, v2_project):
    r = client.post(
        "/api/agent/turn",
        json={
            "text": "What's the gist of this paper?",
            "thread_id": "w2",
            "context_json": {"active_project_id": v2_project.id},
        },
    )
    assert r.status_code == 200
    assert r.json()["graph_write"] is False
    roots = [
        n for n in v2_store.list_nodes(v2_project.id) if n.node_kind.value == "ROOT"
    ]
    assert len(roots) == 0


def test_direct_gist_commit(client, v2_store, v2_project):
    r = client.post(
        "/api/agent/turn",
        json={
            "text": "create root",
            "thread_id": "w2b",
            "context_json": {
                "active_project_id": v2_project.id,
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

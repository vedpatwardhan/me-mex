def test_p1_empty_scope_forces_project_scope_worker(client, empty_project):
    r = client.post(
        "/api/agent/turn",
        json={
            "text": "create root with this gist",
            "thread_id": "p1-gate",
            "context_json": {
                "active_project_id": empty_project.id,
                "custom_fields": {"force_gist_commit": True},
            },
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["worker"] == "project_scope"
    assert body["graph_write"] is False


def test_p1_save_scope(client, store, project):
    r = client.post(
        "/api/agent/turn",
        json={
            "text": "save scope: Robotics manipulation and sim-to-real transfer.",
            "thread_id": "p1",
            "context_json": {"active_project_id": project.id},
        },
    )
    assert r.status_code == 200
    assert r.json()["graph_write"] is True
    assert "manipulation" in store.get_project(project.id).introduction

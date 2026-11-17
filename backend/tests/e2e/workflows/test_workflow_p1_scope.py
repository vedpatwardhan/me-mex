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

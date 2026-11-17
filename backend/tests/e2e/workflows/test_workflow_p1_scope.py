def test_p1_save_scope(client, v2_store, v2_project):
    r = client.post(
        "/api/agent/turn",
        json={
            "text": "save scope: Robotics manipulation and sim-to-real transfer.",
            "thread_id": "p1",
            "context_json": {"active_project_id": v2_project.id},
        },
    )
    assert r.status_code == 200
    assert r.json()["graph_write"] is True
    assert "manipulation" in v2_store.get_project(v2_project.id).introduction

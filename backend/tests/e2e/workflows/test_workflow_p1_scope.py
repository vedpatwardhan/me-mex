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
            "context_json": {
                "active_project_id": project.id,
                "custom_fields": {"force_scope_commit": True},
            },
        },
    )
    assert r.status_code == 200
    assert r.json()["graph_write"] is True
    assert "manipulation" in store.get_project(project.id).introduction


def test_p1_save_scope_proposes_without_force(client, store, project):
    r = client.post(
        "/api/agent/turn",
        json={
            "text": "save scope: Robotics manipulation and sim-to-real transfer.",
            "thread_id": "p1-propose",
            "context_json": {"active_project_id": project.id},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["graph_write"] is False
    assert (body.get("details") or {}).get("approval_id")
    assert not (store.get_project(project.id).introduction or "").strip()


def test_p1_approve_scope_commits(client, store, project):
    r = client.post(
        "/api/agent/turn",
        json={
            "text": "Warehouse pick-and-place with sim-to-real gaps.",
            "thread_id": "p1-approve",
            "context_json": {"active_project_id": project.id},
        },
    )
    assert r.status_code == 200
    aid = (r.json().get("details") or {}).get("approval_id")
    assert aid
    r2 = client.post(
        "/api/agent/resume",
        json={
            "approval_id": aid,
            "action": "approve",
            "thread_id": "p1-approve",
            "context_json": {"active_project_id": project.id},
        },
    )
    assert r2.status_code == 200
    intro = store.get_project(project.id).introduction or ""
    assert "sim-to-real" in intro or "Warehouse" in intro

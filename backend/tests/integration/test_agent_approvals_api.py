def test_list_approvals_empty(client, project_scoped):
    pid = project_scoped.id
    r = client.get("/api/agent/approvals", params={"project_id": pid, "thread_id": "t1"})
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_list_nudges(client, project_scoped):
    pid = project_scoped.id
    r = client.get("/api/agent/nudges", params={"project_id": pid})
    assert r.status_code == 200
    assert "suggestions" in r.json()

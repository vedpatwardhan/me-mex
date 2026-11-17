def test_create_project(client):
    r = client.post("/api/projects?name=Robotics")
    assert r.status_code == 200
    body = r.json()
    assert body["project_id"]
    assert body["genesis_node_id"]

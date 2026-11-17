def test_create_project_v2(client):
    r = client.post("/api/v2/projects?name=Robotics")
    assert r.status_code == 200
    body = r.json()
    assert body["project_id"]
    assert body["genesis_node_id"]

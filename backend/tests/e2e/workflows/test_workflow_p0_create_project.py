def test_create_project(client):
    r = client.post("/api/projects?name=Robotics")
    assert r.status_code == 200
    body = r.json()
    assert body["project_id"]
    assert body["genesis_node_id"]


def test_list_projects_and_graph(client):
    r = client.post("/api/projects?name=ListDemo")
    pid = r.json()["project_id"]
    listed = client.get("/api/projects")
    assert listed.status_code == 200
    ids = {p["id"] for p in listed.json()}
    assert pid in ids

    graph = client.get("/api/graph", params={"project_id": pid})
    assert graph.status_code == 200
    assert len(graph.json()["nodes"]) >= 1

    global_graph = client.get("/api/graph", params={"project_id": "global"})
    assert global_graph.status_code == 200
    assert global_graph.json() == {"nodes": [], "edges": []}

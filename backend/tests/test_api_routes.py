from fastapi.testclient import TestClient


def test_root_endpoint(test_client: TestClient):
    """Test GET / returns system online status."""
    res = test_client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "online"
    assert "nodes_count" in data


def test_projects_endpoints(test_client: TestClient):
    """Test GET /api/projects and POST /api/projects."""
    # Fetch projects
    res = test_client.get("/api/projects")
    assert res.status_code == 200
    projs = res.json()
    assert any((p.get("_id") == "global" or p.get("id") == "global") for p in projs)

    # Create new project workspace
    new_p = {
        "_id": "proj_test_api",
        "name": "API Test Project",
        "description": "Project created during API test",
        "node_ids": [],
        "edge_ids": [],
    }
    post_res = test_client.post("/api/projects", json=new_p)
    assert post_res.status_code == 200
    assert post_res.json()["status"] == "created"

    # Verify project exists
    res_after = test_client.get("/api/projects")
    assert any(
        (p.get("_id") == "proj_test_api" or p.get("id") == "proj_test_api")
        for p in res_after.json()
    )


def test_graph_endpoint(test_client: TestClient):
    """Test GET /api/graph with project_id filtering."""
    res = test_client.get("/api/graph?project_id=global")
    assert res.status_code == 200
    data = res.json()
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) >= 4


def test_chat_endpoint_post(test_client: TestClient):
    """Test POST /api/chat endpoint execution and response schema."""
    chat_payload = {
        "query": "What are latent space world models?",
        "project_id": "global",
        "is_voice": False,
    }
    res = test_client.post("/api/chat", json=chat_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "reply" in data
    assert "intent" in data
    assert "touched_nodes" in data


def test_project_chat_history_endpoint(test_client: TestClient):
    """Test GET /api/projects/{project_id}/chat endpoint."""
    # Send a chat message first
    chat_payload = {
        "query": "Tell me about MPC planning",
        "project_id": "proj_chat_test",
        "is_voice": False,
    }
    test_client.post("/api/chat", json=chat_payload)

    # Retrieve history for proj_chat_test
    res = test_client.get("/api/projects/proj_chat_test/chat")
    assert res.status_code == 200
    messages = res.json()
    assert len(messages) >= 2  # user message + agent reply
    assert messages[0]["project_id"] == "proj_chat_test"

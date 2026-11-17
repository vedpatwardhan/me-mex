from app.models import NodeKind


def test_w3_staging_then_commit(client, v2_store, v2_project_scoped):
    pid = v2_project_scoped.id
    root = client.post(
        "/api/agent/turn",
        json={
            "text": "create root",
            "thread_id": "w3",
            "context_json": {
                "active_project_id": pid,
                "custom_fields": {
                    "title": "Paper",
                    "gist": "Claim",
                    "force_gist_commit": True,
                },
            },
        },
    )
    root_id = root.json()["details"]["result"]["root_id"]
    r = client.post(
        "/api/agent/turn",
        json={
            "text": "deep read this paper",
            "thread_id": "w3",
            "context_json": {
                "active_project_id": pid,
                "custom_fields": {"root_id": root_id},
            },
        },
    )
    assert r.json()["graph_write"] is False
    approval_id = r.json()["details"]["approval_id"]
    assert approval_id
    assert not [
        n for n in v2_store.list_nodes(pid) if n.node_kind == NodeKind.CONCEPT_I
    ]
    done = client.post(
        "/api/agent/resume",
        json={
            "thread_id": "w3",
            "approval_id": approval_id,
            "action": "approve",
            "context_json": {
                "active_project_id": pid,
                "custom_fields": {"root_id": root_id},
            },
        },
    )
    assert done.status_code == 200
    assert len(done.json().get("concept_ids", [])) >= 1

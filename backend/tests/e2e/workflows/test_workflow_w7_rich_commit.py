from app.models import NodeKind


def test_w7_root_then_staging_commit(client, v2_store, v2_project_scoped):
    pid = v2_project_scoped.id
    root = client.post(
        "/api/agent/turn",
        json={
            "text": "create root",
            "thread_id": "w7",
            "context_json": {
                "active_project_id": pid,
                "custom_fields": {
                    "title": "ERA",
                    "gist": "Embodied rollout",
                    "force_gist_commit": True,
                },
            },
        },
    )
    root_id = root.json()["details"]["result"]["root_id"]
    staging = client.post(
        "/api/agent/turn",
        json={
            "text": "deep read staging",
            "thread_id": "w7",
            "context_json": {
                "active_project_id": pid,
                "custom_fields": {"root_id": root_id},
            },
        },
    )
    aid = staging.json()["details"]["approval_id"]
    client.post(
        "/api/agent/resume",
        json={
            "thread_id": "w7",
            "approval_id": aid,
            "action": "approve",
            "context_json": {
                "active_project_id": pid,
                "custom_fields": {"root_id": root_id},
            },
        },
    )
    roots = [n for n in v2_store.list_nodes(pid) if n.node_kind == NodeKind.ROOT]
    concepts = [
        n for n in v2_store.list_nodes(pid) if n.node_kind == NodeKind.CONCEPT_I
    ]
    assert len(roots) >= 1
    assert len(concepts) >= 1

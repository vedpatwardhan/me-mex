from dataclasses import replace
from uuid import uuid4

from app.llm import get_chains, set_chains_override
from app.services.checkpoints import JsonCheckpointStore
from langchain_core.runnables import RunnableLambda


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
    assert r2.json()["scope_committed"] is True
    assert r2.json()["reply"] != "approved"
    assert "Thanks for approving" in r2.json()["reply"]
    intro = store.get_project(project.id).introduction or ""
    assert "sim-to-real" in intro or "Warehouse" in intro


def test_p1_scope_proposal_summarizes_and_revises_conversation(
    client, empty_project, tmpdir_checkpoint, monkeypatch
):
    from app.agents import scope_proposal, session_plane
    from app.api import routes

    checkpoint = JsonCheckpointStore(str(tmpdir_checkpoint))
    monkeypatch.setattr(scope_proposal, "_checkpoint", checkpoint)
    monkeypatch.setattr(session_plane, "_checkpoint", checkpoint)
    monkeypatch.setattr(routes, "_checkpoints", checkpoint)
    payloads = []

    def summarize(inp):
        import json

        payload = json.loads(inp["payload"])
        payloads.append(payload)
        if len(payloads) == 1:
            return "A project on robotic manipulation for warehouse picking."
        return "A project on robust warehouse manipulation, focused on sim-to-real transfer."

    set_chains_override(replace(get_chains(), project_scope=RunnableLambda(summarize)))
    thread_id = f"p1-revisable-summary-{uuid4().hex}"
    for text in (
        "My project scope is robotic manipulation for warehouse picking.",
        "My project scope is actually focused on sim-to-real transfer robustness.",
    ):
        response = client.post(
            "/api/agent/turn",
            json={
                "text": text,
                "thread_id": thread_id,
                "context_json": {"active_project_id": empty_project.id},
            },
        )
        assert response.status_code == 200

    assert payloads[1]["conversation_turns"] == [
        {
            "role": "user",
            "text": "My project scope is robotic manipulation for warehouse picking.",
        },
        {
            "role": "user",
            "text": "My project scope is actually focused on sim-to-real transfer robustness.",
        },
    ]
    assert payloads[1]["draft_proposal"] == (
        "A project on robotic manipulation for warehouse picking."
    )
    approvals = client.get(
        "/api/agent/approvals",
        params={"project_id": empty_project.id, "thread_id": thread_id},
    ).json()["items"]
    assert approvals[-1]["payload"]["proposed_introduction"] == (
        "A project on robust warehouse manipulation, focused on sim-to-real transfer."
    )

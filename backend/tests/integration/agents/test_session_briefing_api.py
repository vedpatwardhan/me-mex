import pytest


@pytest.mark.dock_turn_plane
def test_session_briefing_api(client, project):
    r = client.get(
        "/api/agent/session/briefing",
        params={"project_id": project.id, "thread_id": "t-api"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "active_jobs" in body
    assert "pending_approval_count" in body

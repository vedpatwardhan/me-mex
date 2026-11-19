import pytest
from app.agents.briefing import SessionBriefing


@pytest.mark.voice_plane
def test_session_briefing_keys():
    b: SessionBriefing = {
        "project_scope_snippet": "x",
        "active_jobs": [{"job_id": "j1", "kind": "retrieval", "status": "running"}],
        "last_route": "retrieval",
        "pending_approval_count": 0,
    }
    assert b["active_jobs"][0]["job_id"] == "j1"

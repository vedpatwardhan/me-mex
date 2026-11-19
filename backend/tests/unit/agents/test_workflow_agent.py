import pytest
from app.agents.workflow_agent import run_workflow_agent


@pytest.mark.voice_plane
def test_workflow_agent_proactive_on_approval():
    out = run_workflow_agent(
        job={"job_id": "j1", "worker": "intradoc", "status": "awaiting_approval", "label": "read"},
        worker_output={"approval_id": "appr_x", "reply": "staging ready"},
    )
    assert out["proactive_script"]
    assert out["recommendation_cards"][0]["id"] == "appr_x"

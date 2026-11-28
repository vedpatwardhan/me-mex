import pytest
from app.agents.workflow_agent import run_workflow_agent


@pytest.mark.dock_turn_plane
def test_workflow_agent_proactive_on_approval():
    out = run_workflow_agent(
        job={"job_id": "j1", "worker": "intradoc", "status": "awaiting_approval", "label": "read"},
        worker_output={"approval_id": "appr_x", "reply": "staging ready"},
    )
    assert out["proactive_script"] == ""
    meta = out["proactive_meta"]
    assert meta and meta["kind"] == "review"
    assert meta["worker"] == "intradoc"
    assert "staging ready" not in str(out)
    assert out["recommendation_cards"][0]["id"] == "appr_x"

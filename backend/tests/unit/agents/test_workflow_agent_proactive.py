from app.agents.workflow_agent import run_workflow_agent


def test_scope_done_no_proactive_without_approval():
    out = run_workflow_agent(
        job={"status": "done", "worker": "project_scope", "label": "garbled stt"},
        worker_output={"reply": "ok", "graph_write": False},
    )
    assert out["proactive_script"] == ""


def test_scope_awaiting_approval_nudge():
    out = run_workflow_agent(
        job={"status": "awaiting_approval", "worker": "project_scope", "label": "scope"},
        worker_output={"reply": "draft", "approval_id": "a1"},
    )
    assert "scope" in out["proactive_script"].lower()

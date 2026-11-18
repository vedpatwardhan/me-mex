from app.agents.graph import run_agent_turn


def test_turn_records_job_in_response(store, project_scoped, mock_vllm_chat):
    pid = project_scoped.id
    out = run_agent_turn(
        store=store,
        project_id=pid,
        thread_id="lg-1",
        text="hello",
        context_json={"active_project_id": pid},
    )
    assert out["reply"]
    assert isinstance(out.get("jobs"), list)
    assert len(out["jobs"]) >= 1
    assert out["jobs"][0].get("worker")

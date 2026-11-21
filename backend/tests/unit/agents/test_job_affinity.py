from app.agents.job_affinity import resolve_job_dispatch


def test_scope_second_turn_updates_same_job():
    jobs = [
        {
            "job_id": "j1",
            "affinity_key": "scope:pid",
            "status": "awaiting_approval",
            "approval_id": "a1",
        }
    ]
    plan = resolve_job_dispatch(
        thread_id="t",
        project_id="pid",
        worker_kind="project_scope",
        effective_text="More detail on sim-to-real.",
        context_json={},
        jobs=jobs,
        pending_approvals=[],
        introduction="",
        dispatch_allowed=True,
    )
    assert plan.action == "update"
    assert plan.job_id == "j1"
    assert plan.affinity_key == "scope:pid"


def test_dialogue_skips_dispatch():
    plan = resolve_job_dispatch(
        thread_id="t",
        project_id="pid",
        worker_kind="conversation",
        effective_text="hi",
        context_json={},
        jobs=[],
        pending_approvals=[],
        introduction="",
        dispatch_allowed=False,
    )
    assert plan.action == "skip"

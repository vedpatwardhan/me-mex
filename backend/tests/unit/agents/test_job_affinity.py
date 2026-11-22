from app.agents.job_affinity import affinity_key_for_worker, resolve_job_dispatch


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


def test_repeated_source_request_does_not_restart_a_running_gist_job():
    context = {
        "custom_fields": {"paper": "https://example.test/paper.pdf"},
        "supervisor_decision": {
            "source_field": "paper",
            "source_reference": "https://example.test/paper.pdf",
        },
    }
    affinity_key = affinity_key_for_worker(
        "gist",
        project_id="pid",
        context_json=context,
    )
    plan = resolve_job_dispatch(
        thread_id="t",
        project_id="pid",
        worker_kind="gist",
        effective_text="Give me a broad summary of the paper.",
        context_json=context,
        jobs=[
            {
                "job_id": "gist-running",
                "worker": "gist",
                "status": "running",
                "affinity_key": affinity_key,
                "request_text": "Summarize this paper",
            }
        ],
        pending_approvals=[],
        introduction="Research paper project.",
        dispatch_allowed=True,
    )

    assert plan.action == "skip"
    assert plan.job_id == "gist-running"
    assert plan.reason == "already_running"


def test_link_affinity_uses_resolved_source_and_target_nodes():
    first = affinity_key_for_worker(
        "link",
        project_id="pid",
        context_json={
            "supervisor_decision": {
                "root_id": "root-a",
                "target_ids": ["node-b", "node-c"],
            }
        },
    )
    same_link_reordered = affinity_key_for_worker(
        "link",
        project_id="pid",
        context_json={
            "supervisor_decision": {
                "root_id": "root-a",
                "target_ids": ["node-c", "node-b"],
            }
        },
    )
    different_link = affinity_key_for_worker(
        "link",
        project_id="pid",
        context_json={
            "supervisor_decision": {
                "root_id": "root-a",
                "target_ids": ["node-d"],
            }
        },
    )

    assert first == same_link_reordered
    assert first != different_link


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

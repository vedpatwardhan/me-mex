from types import SimpleNamespace

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


def test_intradoc_affinity_distinguishes_url_only_sources_and_skips_only_duplicates():
    def context(url: str) -> dict:
        return {
            "custom_fields": {"paper": url},
            "supervisor_decision": {"source_field": "paper", "source_reference": url},
        }

    first_context = context("https://example.test/first.pdf")
    second_context = context("https://example.test/second.pdf")
    first_key = affinity_key_for_worker("intradoc", project_id="pid", context_json=first_context)
    second_key = affinity_key_for_worker("intradoc", project_id="pid", context_json=second_context)
    running = {
        "job_id": "intradoc-first",
        "worker": "intradoc",
        "status": "running",
        "affinity_key": first_key,
    }

    different_source = resolve_job_dispatch(
        thread_id="t",
        project_id="pid",
        worker_kind="intradoc",
        effective_text="Deep read this other paper",
        context_json=second_context,
        jobs=[running],
        pending_approvals=[],
        dispatch_allowed=True,
    )
    duplicate = resolve_job_dispatch(
        thread_id="t",
        project_id="pid",
        worker_kind="intradoc",
        effective_text="Deep read the first paper again",
        context_json=first_context,
        jobs=[running],
        pending_approvals=[],
        dispatch_allowed=True,
    )

    assert first_key != second_key
    assert different_source.action == "create"
    assert duplicate.action == "skip"
    assert duplicate.job_id == "intradoc-first"


def test_pending_approval_for_different_source_does_not_capture_new_job():
    first_context = {
        "custom_fields": {"paper": "https://example.test/first.pdf"},
        "supervisor_decision": {
            "source_field": "paper",
            "source_reference": "https://example.test/first.pdf",
        },
    }
    second_context = {
        "custom_fields": {"paper": "https://example.test/second.pdf"},
        "supervisor_decision": {
            "source_field": "paper",
            "source_reference": "https://example.test/second.pdf",
        },
    }
    pending = SimpleNamespace(
        approval_type="gist_root",
        status="pending",
        id="approval-first",
        payload={
            "affinity_key": affinity_key_for_worker(
                "gist", project_id="pid", context_json=first_context
            )
        },
    )

    plan = resolve_job_dispatch(
        thread_id="t",
        project_id="pid",
        worker_kind="gist",
        effective_text="Summarize the second paper",
        context_json=second_context,
        jobs=[],
        pending_approvals=[pending],
        dispatch_allowed=True,
    )

    assert plan.action == "create"
    assert plan.approval_id is None

    same_source = resolve_job_dispatch(
        thread_id="t",
        project_id="pid",
        worker_kind="gist",
        effective_text="Give another summary of the first paper",
        context_json=first_context,
        jobs=[],
        pending_approvals=[pending],
        dispatch_allowed=True,
    )
    assert same_source.action == "update"
    assert same_source.approval_id == "approval-first"


def test_duplicate_job_with_pending_approval_does_not_restart_worker():
    context = {
        "custom_fields": {"paper": "https://example.test/paper.pdf"},
        "supervisor_decision": {
            "source_field": "paper",
            "source_reference": "https://example.test/paper.pdf",
        },
    }
    affinity = affinity_key_for_worker("gist", project_id="pid", context_json=context)
    plan = resolve_job_dispatch(
        thread_id="t",
        project_id="pid",
        worker_kind="gist",
        effective_text="Summarize this paper again",
        context_json=context,
        jobs=[
            {
                "job_id": "gist-awaiting-review",
                "worker": "gist",
                "status": "awaiting_approval",
                "affinity_key": affinity,
                "approval_id": "approval-gist",
            }
        ],
        pending_approvals=[],
        dispatch_allowed=True,
    )

    assert plan.action == "skip"
    assert plan.approval_id == "approval-gist"
    assert plan.reason == "pending_approval_match"


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

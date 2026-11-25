from app.agents.supervisor_plan_contract import (
    plan_incomplete,
    routing_binding_hints,
    should_append_supervisor_reply,
    supervisor_max_tokens,
)
from app.llm.schemas import DispatchTask, WorkerRoute


def test_plan_incomplete_three_urls_conversation_clarify():
    decision = WorkerRoute(
        worker="conversation",
        intent="conversation",
        dispatch=False,
        reply="Which paper first?",
    )
    ctx = {
        "custom_fields": {
            "paper1": "https://arxiv.org/pdf/2601.00001",
            "paper2": "https://arxiv.org/pdf/2601.00002",
        }
    }
    assert plan_incomplete(decision, ctx) is True


def test_plan_incomplete_with_dispatch_tasks_false():
    decision = WorkerRoute(
        worker="conversation",
        intent="conversation",
        dispatch=False,
        multi_action=True,
        dispatch_tasks=[
            DispatchTask(
                worker="gist",
                intent="source_summary",
                dispatch=True,
                source_field="paper1",
                source_reference="https://arxiv.org/pdf/2601.00001",
            ),
        ],
    )
    ctx = {
        "custom_fields": {
            "paper1": "https://arxiv.org/pdf/2601.00001",
            "paper2": "https://arxiv.org/pdf/2601.00002",
        }
    }
    assert plan_incomplete(decision, ctx) is False


def test_routing_binding_hints_lists_fields_and_jobs():
    hints = routing_binding_hints(
        {
            "custom_fields": {"paper1": "https://arxiv.org/pdf/2601.00001"},
            "session_state": {
                "active_jobs": [{"job_id": "job_x", "worker": "gist", "status": "running"}]
            },
        }
    )
    assert hints["url_field_rows"][0]["field"] == "paper1"
    assert hints["job_rows"][0]["job_id"] == "job_x"


def test_should_append_reply_only_with_tasks_and_executable():
    partial = WorkerRoute(
        worker="conversation",
        intent="conversation",
        dispatch=False,
        reply="Which field is the third paper?",
        dispatch_tasks=[
            DispatchTask(
                worker="gist",
                intent="source_summary",
                dispatch=True,
                source_field="paper1",
            ),
        ],
    )
    assert should_append_supervisor_reply(partial, had_executable_tasks=True) is True
    assert should_append_supervisor_reply(partial, had_executable_tasks=False) is False
    clarify_only = WorkerRoute(
        worker="conversation",
        intent="conversation",
        dispatch=False,
        reply="Which paper?",
    )
    assert should_append_supervisor_reply(clarify_only, had_executable_tasks=True) is False


def test_structural_multi_url_fallback_builds_three_tasks():
    from app.agents.supervisor_plan_contract import structural_multi_url_dispatch_fallback

    decision = WorkerRoute(
        worker="conversation",
        intent="conversation",
        dispatch=False,
        reply="I'll summarize them.",
    )
    ctx = {
        "custom_fields": {
            "paper1": "https://arxiv.org/pdf/2601.00001",
            "paper2": "https://arxiv.org/pdf/2601.00002",
            "paper3": "https://arxiv.org/pdf/2601.00003",
        }
    }
    out = structural_multi_url_dispatch_fallback(decision, ctx)
    assert len(out.dispatch_tasks) == 3
    assert out.dispatch_tasks[2].worker == "intradoc"


def test_supervisor_max_tokens_scales_with_url_fields():
    assert supervisor_max_tokens({}) == 512
    assert (
        supervisor_max_tokens(
            {
                "custom_fields": {
                    "a": "https://a",
                    "b": "https://b",
                    "c": "https://c",
                }
            }
        )
        >= 512
    )

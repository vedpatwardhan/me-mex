"""Live Supervisor regressions for multi-action dispatch_tasks (requires .env.test live Colab)."""

import pytest
from app.agents.supervisor_plan_contract import plan_incomplete
from app.agents.workers import route_intent
from app.config import settings
from app.models import Project

pytestmark = pytest.mark.live_llm


def _skip_unless_live():
    if settings.CHAT_LLM_MODE != "live":
        pytest.skip("CHAT_LLM_MODE is not live (set in backend/.env.test)")
    if not settings.colab_inference_configured:
        pytest.skip("COLAB_INFERENCE_BASE_URL is not set in backend/.env.test")


THREE_PAPER_TEXT = (
    "I've just attached links to 3 different papers. "
    "I'd like a broad high level summary of the first 2 papers and "
    "a detailed understanding of the 3rd paper."
)

THREE_PAPER_FIELDS = {
    "paper1": "https://arxiv.org/pdf/2605.11550",
    "paper2": "https://arxiv.org/pdf/2610.20951",
    "paper3": "https://arxiv.org/pdf/2610.38568",
}


@pytest.mark.live_llm
def test_live_supervisor_three_paper_mixed_dispatch_tasks():
    _skip_unless_live()
    project = Project(
        _id="live-three-paper",
        name="RSI",
        introduction="Research on recursive self-improvement in AI systems.",
    )
    ctx = {
        "custom_fields": THREE_PAPER_FIELDS,
        "project_scope_status": "committed",
        "scope_approval_pending": False,
        "session_state": {
            "active_jobs": [],
            "recent_jobs": [],
            "pending_approval_count": 0,
            "completed_worker_results": [],
        },
    }
    decision = route_intent(THREE_PAPER_TEXT, ctx, project)
    assert not plan_incomplete(decision, ctx), decision.model_dump()
    assert len(decision.dispatch_tasks) == 3, decision.model_dump()
    workers = {t.worker for t in decision.dispatch_tasks}
    assert workers == {"gist", "intradoc"}
    gist_count = sum(1 for t in decision.dispatch_tasks if t.worker == "gist")
    assert gist_count == 2
    fields = {t.source_field for t in decision.dispatch_tasks}
    assert fields == {"paper1", "paper2", "paper3"}


@pytest.mark.live_llm
def test_live_supervisor_multi_job_control_dispatch_tasks():
    _skip_unless_live()
    project = Project(_id="live-multi-jc", name="n", introduction="Research project.")
    ctx = {
        "custom_fields": {},
        "session_state": {
            "active_jobs": [
                {
                    "job_id": "job_resume_me",
                    "worker": "gist",
                    "status": "paused",
                    "label": "Paper A",
                },
                {
                    "job_id": "job_cancel_me",
                    "worker": "intradoc",
                    "status": "running",
                    "label": "Paper B",
                },
            ],
            "recent_jobs": [],
            "pending_approval_count": 0,
        },
    }
    decision = route_intent(
        "Resume the paused gist job for paper A and cancel the running intradoc for paper B.",
        ctx,
        project,
    )
    if decision.dispatch_tasks:
        assert len(decision.dispatch_tasks) >= 2
        actions = {t.job_action for t in decision.dispatch_tasks if t.job_action}
        assert "resume" in actions
        assert "cancel" in actions
    else:
        assert decision.worker == "job_control" or not plan_incomplete(decision, ctx)

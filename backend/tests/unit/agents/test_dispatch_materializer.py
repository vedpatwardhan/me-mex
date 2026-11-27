from app.agents.dispatch_materializer import materialize_dispatches
from app.llm.schemas import DispatchTask, WorkerRoute

_GIST = WorkerRoute(
    worker="gist",
    intent="source_summary",
    dispatch=True,
    reply=None,
)


def test_single_reference_unchanged():
    text = "gist https://arxiv.org/pdf/2601.00001"
    r = materialize_dispatches(
        _GIST, effective_text=text, custom_fields={}, session_jobs={}, dispatch_allowed=True
    )
    assert len(r.decisions) == 1
    assert r.clarification is None


def test_fan_out_same_worker_homogeneous():
    fields = {
        "paper1": "https://arxiv.org/pdf/2601.00001",
        "paper2": "https://arxiv.org/pdf/2601.00002",
        "paper3": "https://arxiv.org/pdf/2601.00003",
    }
    decision = WorkerRoute(
        worker="gist",
        intent="source_summary",
        dispatch=True,
        fan_out_same_worker=True,
    )
    r = materialize_dispatches(
        decision,
        effective_text="gist all attached papers",
        custom_fields=fields,
        session_jobs={},
        dispatch_allowed=True,
    )
    assert r.clarification is None
    assert len(r.decisions) == 3
    assert {d.source_field for d in r.decisions} == {"paper1", "paper2", "paper3"}


def test_dispatch_tasks_mixed_workers():
    fields = {
        "paper1": "https://arxiv.org/pdf/2601.00001",
        "paper2": "https://arxiv.org/pdf/2601.00002",
        "paper3": "https://arxiv.org/pdf/2601.00003",
    }
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
            DispatchTask(
                worker="gist",
                intent="source_summary",
                dispatch=True,
                source_field="paper2",
                source_reference="https://arxiv.org/pdf/2601.00002",
            ),
            DispatchTask(
                worker="intradoc",
                intent="source_analysis",
                dispatch=True,
                source_field="paper3",
                source_reference="https://arxiv.org/pdf/2601.00003",
            ),
        ],
    )
    r = materialize_dispatches(
        decision,
        effective_text="mixed summaries",
        custom_fields=fields,
        session_jobs={},
        dispatch_allowed=True,
    )
    assert r.clarification is None
    assert len(r.decisions) == 3
    workers = {d.worker for d in r.decisions}
    assert workers == {"gist", "intradoc"}


def test_conversation_clarify_with_multiple_urls_materializer_gate():
    fields = {
        "paper1": "https://arxiv.org/pdf/2601.00001",
        "paper2": "https://arxiv.org/pdf/2601.00002",
    }
    decision = WorkerRoute(
        worker="conversation",
        intent="conversation",
        dispatch=False,
        reply="Which paper first?",
    )
    r = materialize_dispatches(
        decision,
        effective_text="summarize both",
        custom_fields=fields,
        session_jobs={},
        dispatch_allowed=True,
    )
    assert r.decisions == []
    assert r.clarification is not None
    assert r.clarification.code == "multi_source_plan_required"


def test_multi_action_gate_single_pinned_field_clarifies():
    fields = {
        "paper1": "https://arxiv.org/pdf/2601.00001",
        "paper2": "https://arxiv.org/pdf/2601.00002",
    }
    pinned = WorkerRoute(
        worker="gist",
        intent="source_summary",
        dispatch=True,
        multi_action=True,
        source_field="paper1",
        source_reference="https://arxiv.org/pdf/2601.00001",
    )
    r = materialize_dispatches(
        pinned,
        effective_text="gist both",
        custom_fields=fields,
        session_jobs={},
        dispatch_allowed=True,
    )
    assert r.decisions == []
    assert r.clarification is not None
    assert r.clarification.code == "multi_source_plan_required"


def test_job_control_requires_known_job_id():
    decision = WorkerRoute(
        worker="job_control",
        intent="job_control",
        dispatch=True,
        multi_action=True,
        dispatch_tasks=[
            DispatchTask(
                worker="job_control",
                intent="job_control",
                dispatch=True,
                target_id="job_unknown",
                job_action="pause",
            ),
        ],
    )
    r = materialize_dispatches(
        decision,
        effective_text="pause that job",
        custom_fields={},
        session_jobs={"active_jobs": [{"job_id": "job_abc", "worker": "gist"}]},
        dispatch_allowed=True,
    )
    assert r.decisions == []
    assert r.clarification is not None
    assert r.clarification.code == "job_id_unknown"


def test_job_control_tasks_materialize():
    decision = WorkerRoute(
        worker="conversation",
        intent="conversation",
        dispatch=False,
        multi_action=True,
        dispatch_tasks=[
            DispatchTask(
                worker="job_control",
                intent="job_control",
                dispatch=True,
                target_id="job_abc",
                job_action="resume",
            ),
            DispatchTask(
                worker="job_control",
                intent="job_control",
                dispatch=True,
                target_id="job_def",
                job_action="delete",
            ),
        ],
    )
    session = {
        "active_jobs": [
            {"job_id": "job_abc", "worker": "gist"},
            {"job_id": "job_def", "worker": "intradoc"},
        ]
    }
    r = materialize_dispatches(
        decision,
        effective_text="resume one and delete the other",
        custom_fields={},
        session_jobs=session,
        dispatch_allowed=True,
    )
    assert r.clarification is None
    assert len(r.decisions) == 2
    assert {d.target_id for d in r.decisions} == {"job_abc", "job_def"}

from app.agents.context_preprocessor import apply_custom_fields_to_text
from app.agents.multi_source_planner import plan_multi_source_tasks
from app.llm.schemas import WorkerRoute

_TRACE_TEXT = (
    "I have just attached a link to three different papers. "
    "I need a high level summary of the first two papers and I need a "
    "detailed understanding of the third paper."
)
_TRACE_FIELDS = {
    "paper1": "https://arxiv.org/pdf/2605.11550",
    "paper2": "https://arxiv.org/pdf/2610.20951",
    "paper3": "https://arxiv.org/pdf/2610.38568",
}
_TRACE_SUPERVISOR = WorkerRoute(
    worker="gist",
    intent="source_summary",
    dispatch=True,
    source_field="paper1",
    source_reference="https://arxiv.org/pdf/2605.11550",
)


def test_trace_style_three_paper_mixed_dispatch_with_appended_fields():
    effective = apply_custom_fields_to_text(_TRACE_TEXT, {"custom_fields": _TRACE_FIELDS})
    result = plan_multi_source_tasks(
        _TRACE_SUPERVISOR,
        effective_text=effective,
        custom_fields=_TRACE_FIELDS,
        dispatch_allowed=True,
    )
    assert result is not None
    assert [d.worker for d in result.decisions] == ["gist", "gist", "intradoc"]


def test_trace_style_three_paper_mixed_dispatch():
    result = plan_multi_source_tasks(
        _TRACE_SUPERVISOR,
        effective_text=_TRACE_TEXT,
        custom_fields=_TRACE_FIELDS,
        dispatch_allowed=True,
    )
    assert result is not None
    assert result.clarification is None
    assert len(result.decisions) == 3
    assert [d.worker for d in result.decisions] == ["gist", "gist", "intradoc"]
    assert [d.source_field for d in result.decisions] == ["paper1", "paper2", "paper3"]
    urls = {d.source_reference for d in result.decisions}
    assert urls == set(_TRACE_FIELDS.values())


def test_three_urls_ambiguous_mixed_clarifies():
    fields = {
        "paper1": "https://arxiv.org/pdf/2601.00001",
        "paper2": "https://arxiv.org/pdf/2601.00002",
        "paper3": "https://arxiv.org/pdf/2601.00003",
    }
    text = "I attached three papers — give me a summary and a detailed read."
    result = plan_multi_source_tasks(
        _TRACE_SUPERVISOR,
        effective_text=text,
        custom_fields=fields,
        dispatch_allowed=True,
    )
    assert result is not None
    assert result.decisions == []
    assert result.clarification


def test_single_url_planner_defers():
    result = plan_multi_source_tasks(
        _TRACE_SUPERVISOR,
        effective_text="gist this one",
        custom_fields={"paper1": "https://arxiv.org/pdf/2601.00001"},
        dispatch_allowed=True,
    )
    assert result is None


def test_homogeneous_multi_gist_planner_defers():
    fields = {
        "paper1": "https://arxiv.org/pdf/2601.00001",
        "paper2": "https://arxiv.org/pdf/2601.00002",
    }
    text = "Please gist both papers"
    result = plan_multi_source_tasks(
        _TRACE_SUPERVISOR,
        effective_text=text,
        custom_fields=fields,
        dispatch_allowed=True,
    )
    assert result is None

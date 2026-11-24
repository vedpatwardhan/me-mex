from app.agents.multi_source_dispatch import expand_source_dispatches
from app.llm.schemas import WorkerRoute

_GIST = WorkerRoute(
    worker="gist",
    intent="source_summary",
    dispatch=True,
    reply=None,
)


def test_single_reference_unchanged():
    text = "gist https://arxiv.org/pdf/2601.00001"
    r = expand_source_dispatches(
        _GIST, effective_text=text, custom_fields={}, dispatch_allowed=True
    )
    assert len(r.decisions) == 1
    assert r.clarification is None


def test_multi_with_both_cue():
    fields = {"a": "https://arxiv.org/pdf/2601.00001", "b": "https://arxiv.org/pdf/2601.00002"}
    text = "Please gist both papers"
    r = expand_source_dispatches(
        _GIST, effective_text=text, custom_fields=fields, dispatch_allowed=True
    )
    assert r.clarification is None
    assert len(r.decisions) == 2
    refs = {d.source_reference for d in r.decisions}
    assert len(refs) == 2


def test_multi_without_cue_clarifies():
    fields = {"a": "https://arxiv.org/pdf/2601.00001", "b": "https://arxiv.org/pdf/2601.00002"}
    text = "gist the first one"
    r = expand_source_dispatches(
        _GIST, effective_text=text, custom_fields=fields, dispatch_allowed=True
    )
    assert r.decisions == []
    assert r.clarification


def test_pinned_field_homogeneous_multi_fans_out():
    fields = {
        "paper1": "https://arxiv.org/pdf/2601.00001",
        "paper2": "https://arxiv.org/pdf/2601.00002",
        "paper3": "https://arxiv.org/pdf/2601.00003",
    }
    pinned = WorkerRoute(
        worker="gist",
        intent="source_summary",
        dispatch=True,
        source_field="paper1",
        source_reference="https://arxiv.org/pdf/2601.00001",
    )
    text = "Please gist all three attached papers"
    r = expand_source_dispatches(
        pinned, effective_text=text, custom_fields=fields, dispatch_allowed=True
    )
    assert r.clarification is None
    assert len(r.decisions) == 3
    assert {d.source_field for d in r.decisions} == {"paper1", "paper2", "paper3"}


def test_pinned_field_mixed_workers_stays_single():
    fields = {
        "paper1": "https://arxiv.org/pdf/2601.00001",
        "paper2": "https://arxiv.org/pdf/2601.00002",
        "paper3": "https://arxiv.org/pdf/2601.00003",
    }
    pinned = WorkerRoute(
        worker="gist",
        intent="source_summary",
        dispatch=True,
        source_field="paper1",
        source_reference="https://arxiv.org/pdf/2601.00001",
    )
    text = (
        "high level summary of the first two papers and a detailed understanding of the third paper"
    )
    r = expand_source_dispatches(
        pinned, effective_text=text, custom_fields=fields, dispatch_allowed=True
    )
    assert len(r.decisions) == 1
    assert r.decisions[0].source_field == "paper1"

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

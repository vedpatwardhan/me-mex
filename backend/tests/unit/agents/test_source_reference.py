from dataclasses import replace

from app.agents import workers
from app.agents.source_reference import resolve_source_reference
from app.agents.workers import _summarize_source
from app.db import ToolContext
from app.llm import get_chains, set_chains_override
from app.llm.schemas import WorkerRoute
from langchain_core.runnables import RunnableLambda


def test_source_reference_uses_url_value_independent_of_custom_field_name():
    ref = resolve_source_reference(
        "Give me a short summary of the linked paper.",
        {"reading_material": "https://arxiv.org/abs/2605.11550"},
        selected_reference="https://arxiv.org/abs/2605.11550",
        selected_field="reading_material",
    )
    assert ref.url == "https://arxiv.org/pdf/2605.11550"
    assert ref.error is None


def test_source_reference_resolves_arxiv_id_from_arbitrary_field():
    ref = resolve_source_reference("Summarize this paper", {"source_key": "2605.11550"})
    assert ref.url == "https://arxiv.org/pdf/2605.11550"


def test_source_reference_reports_multiple_links():
    ref = resolve_source_reference(
        "Summarize these sources",
        {"first": "https://example.com/a", "second": "https://example.com/b"},
    )
    assert ref.url is None
    assert "multiple" in (ref.error or "")


def test_supervisor_selected_reference_must_be_user_supplied():
    ref = resolve_source_reference(
        "Summarize the attached paper.",
        {"reading_material": "https://example.org/paper.pdf"},
        selected_reference="https://example.org/other-paper.pdf",
        selected_field="reading_material",
    )
    assert ref.url is None
    assert "does not match" in (ref.error or "")


def test_supervisor_route_resolves_summary_and_deep_analysis_intents(project):
    gist_context = {"custom_fields": {"paper": "https://arxiv.org/pdf/2605.11550"}}
    summary = workers.route_intent("Give me a brief summary", gist_context, project)
    detailed = workers.route_intent("Give me a detailed analysis", gist_context, project)
    assert (summary.worker, summary.intent, summary.dispatch) == ("gist", "source_summary", True)
    assert summary.source_field == "paper"
    assert summary.source_reference == "https://arxiv.org/pdf/2605.11550"
    assert (detailed.worker, detailed.intent, detailed.dispatch) == (
        "intradoc",
        "source_analysis",
        True,
    )


def test_supervisor_source_selection_is_validated_against_arbitrary_custom_field(
    project,
):
    base = get_chains()
    source_url = "https://example.org/selected.pdf"
    set_chains_override(
        replace(
            base,
            supervisor=RunnableLambda(
                lambda _inputs: WorkerRoute(
                    worker="gist",
                    intent="source_summary",
                    dispatch=True,
                    source_field="background_reading",
                    source_reference=source_url,
                )
            ),
        )
    )
    decision = workers.route_intent(
        "Please summarize the paper I attached.",
        {"custom_fields": {"background_reading": source_url}},
        project,
    )
    assert decision.source_field == "background_reading"
    assert decision.source_reference == source_url
    assert decision.source_error is None


def test_supervisor_source_selection_cannot_invent_a_url(project):
    base = get_chains()
    set_chains_override(
        replace(
            base,
            supervisor=RunnableLambda(
                lambda _inputs: WorkerRoute(
                    worker="gist",
                    intent="source_summary",
                    dispatch=True,
                    source_field="reading_material",
                    source_reference="https://example.org/invented.pdf",
                )
            ),
        )
    )
    decision = workers.route_intent(
        "Summarize the attached paper.",
        {"custom_fields": {"reading_material": "https://example.org/supplied.pdf"}},
        project,
    )
    assert decision.source_reference is None
    assert "does not match" in (decision.source_error or "")


def test_substantive_scope_draft_dispatches_even_if_supervisor_misses_dispatch_bit(empty_project):
    base = get_chains()
    decision = WorkerRoute(
        worker="project_scope",
        intent="scope_conversation",
        dispatch=False,
        content=(
            "The project studies recursive self-improvement in AI, including autonomous "
            "changes to algorithms, infrastructure, and research workflows."
        ),
    )
    set_chains_override(replace(base, supervisor=RunnableLambda(lambda _inputs: decision)))

    resolved = workers.route_intent(
        "My project is about recursive self-improvement in AI and research methods.",
        {},
        empty_project,
    )

    assert resolved.worker == "project_scope"
    assert resolved.dispatch is True


def test_short_scope_chit_chat_does_not_dispatch_approval_job(empty_project):
    base = get_chains()
    decision = WorkerRoute(
        worker="project_scope",
        intent="scope_conversation",
        dispatch=False,
        content="the",
    )
    set_chains_override(replace(base, supervisor=RunnableLambda(lambda _inputs: decision)))

    resolved = workers.route_intent("the", {}, empty_project)

    assert resolved.worker == "project_scope"
    assert resolved.dispatch is False


def test_gist_worker_fetches_resolved_source_and_summarizes_extracted_text(
    store, project, monkeypatch
):
    fetched_urls = []
    summarized = []

    def fetch(_ctx, url):
        fetched_urls.append(url)
        return {
            "text": "# Paper from May 2026\n\nThe paper's actual methods and results.",
            "content_hash": "source-content-hash",
            "url": url,
            "status": "SUCCESS",
        }

    def summarize(inputs):
        summarized.append(inputs)
        return "A concise, source-grounded summary of the May 2026 paper."

    monkeypatch.setattr(workers.fetch_tool, "fetch_normalized_text", fetch)
    set_chains_override(replace(get_chains(), gist_draft=RunnableLambda(summarize)))

    ctx = ToolContext(project_id=project.id, thread_id="gist-source", store=store)
    out = workers.gist_worker(
        ctx,
        "Give me a short summary of this paper.",
        {"custom_fields": {"paper": "https://arxiv.org/abs/2605.11550"}},
    )

    assert fetched_urls == ["https://arxiv.org/pdf/2605.11550"]
    assert summarized[0]["source_title"] == "Paper from May 2026"
    assert "actual methods and results" in summarized[0]["text"]
    assert out["source_summary"] == "A concise, source-grounded summary of the May 2026 paper."
    assert out["source_url"] == fetched_urls[0]
    assert out["graph_write"] is False


def test_gist_worker_does_not_summarize_request_when_fetch_is_empty(store, project, monkeypatch):
    called = False

    def fetch(_ctx, url):
        return {"text": "", "content_hash": "", "url": url, "status": "ERROR"}

    def summarize(_inputs):
        nonlocal called
        called = True
        return "Hallucinated summary"

    monkeypatch.setattr(workers.fetch_tool, "fetch_normalized_text", fetch)
    set_chains_override(replace(get_chains(), gist_draft=RunnableLambda(summarize)))
    ctx = ToolContext(project_id=project.id, thread_id="gist-empty", store=store)

    out = workers.gist_worker(
        ctx,
        "Give me a short summary of this paper.",
        {"custom_fields": {"paper": "https://arxiv.org/pdf/2605.11550"}},
    )

    assert out["error"] is True
    assert out.get("source_summary") is None
    assert called is False


def test_intradoc_uses_same_field_independent_source_resolution(store, project, monkeypatch):
    fetched_urls = []

    def fetch(_ctx, url):
        fetched_urls.append(url)
        return {
            "text": "# Detailed Paper\n\nFull extracted text for concept analysis.",
            "content_hash": "intradoc-content-hash",
            "url": url,
            "status": "SUCCESS",
        }

    monkeypatch.setattr(workers.fetch_tool, "fetch_normalized_text", fetch)
    base = get_chains()
    set_chains_override(
        replace(
            base,
            intradoc=RunnableLambda(
                lambda inputs: [
                    {
                        "concept_id": "concept-1",
                        "title": "Actual paper concept",
                        "description": inputs["text"],
                    }
                ]
            ),
        )
    )
    ctx = ToolContext(project_id=project.id, thread_id="intradoc-source", store=store)

    out = workers.intradoc_worker(
        ctx,
        "Please provide a detailed analysis of the linked paper.",
        {"custom_fields": {"reading_material": "https://arxiv.org/abs/2605.11550"}},
    )

    assert fetched_urls == ["https://arxiv.org/pdf/2605.11550"]
    assert out["approval_id"]
    approval = store.list_pending(project.id, "intradoc-source")[-1]
    staging_bundle = store.get_staging(approval.payload["staging_key"])
    assert staging_bundle.pending_url == fetched_urls[0]
    assert staging_bundle.content_hash == "intradoc-content-hash"
    assert staging_bundle.concepts[0].title == "Actual paper concept"


def test_long_source_gist_uses_map_reduce_summaries(monkeypatch):
    inputs_seen = []

    def summarize(inputs):
        inputs_seen.append(inputs)
        return f"summary-{len(inputs_seen)}"

    set_chains_override(replace(get_chains(), gist_draft=RunnableLambda(summarize)))
    chunk_size = 12000
    long_document = "Research finding. " * (chunk_size // len("Research finding. ") * 2)
    result = _summarize_source(
        long_document,
        source_title="Long paper",
        source_url="https://example.com/paper.pdf",
        project_scope="",
    )

    assert len(inputs_seen) > 2
    assert any("excerpt" in item["summary_stage"].lower() for item in inputs_seen)
    assert "whole-document gist" in inputs_seen[-1]["summary_stage"]
    assert result == f"summary-{len(inputs_seen)}"

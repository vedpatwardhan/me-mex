from app.db import ToolContext
from app.tools import fetch


def test_fetch_local_file(store, project, tmp_path):
    p = tmp_path / "note.txt"
    p.write_text("Hello normalized fetch fixture.", encoding="utf-8")
    ctx = ToolContext(project_id=project.id, thread_id="f1", store=store)
    out = fetch.fetch_normalized_text(ctx, f"file://{p}")
    assert "Hello normalized" in out["text"]
    assert len(out["content_hash"]) == 16


def test_fetch_does_not_search_arxiv_when_supplied_document_is_unreadable(
    store, project, monkeypatch
):
    from app.tools.search_tools import SearchTools

    monkeypatch.setattr(
        SearchTools,
        "fetch_document",
        lambda _url: {"content": "", "status": "ERROR", "error": "unreadable PDF"},
    )

    def unexpected_search(*_args, **_kwargs):
        raise AssertionError("fetch must not search for a substitute source")

    monkeypatch.setattr(SearchTools, "search_arxiv", unexpected_search)
    ctx = ToolContext(project_id=project.id, thread_id="f2", store=store)
    out = fetch.fetch_normalized_text(ctx, "https://arxiv.org/pdf/2605.11550")

    assert out["text"] == ""
    assert out["status"] == "ERROR"
    assert out["error"] == "unreadable PDF"

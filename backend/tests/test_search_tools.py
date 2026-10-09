from pathlib import Path
from app.tools.search_tools import search_tools


def test_fetch_document_pdf_url():
    """Verify SearchTools.fetch_document extracts binary PDF content directly via pypdf and persists debug markdown."""
    url = "https://arxiv.org/pdf/2605.11550"
    res = search_tools.fetch_document(url)

    assert (
        res.get("status") == "SUCCESS"
    ), f"Expected SUCCESS but got {res.get('status')}: {res.get('error')}"
    assert "content" in res and len(res["content"]) > 1000
    assert "debug_file_path" in res
    debug_path = res["debug_file_path"]
    assert debug_path != "", "debug_file_path should not be empty"

    file_obj = Path(debug_path)
    assert file_obj.exists(), f"Debug file {debug_path} should exist on disk"
    assert file_obj.is_file(), f"{debug_path} should be a file"

    content = file_obj.read_text(encoding="utf-8")
    assert f"<!-- Source URL: {url} -->" in content
    assert "<!-- Character Count:" in content


def test_fetch_document_html_blog_url():
    """Verify SearchTools.fetch_document extracts clean article markdown from real HTML web blogs via trafilatura."""
    url = "https://paulgraham.com/greatwork.html"
    res = search_tools.fetch_document(url)

    assert (
        res.get("status") == "SUCCESS"
    ), f"Expected SUCCESS but got {res.get('status')}: {res.get('error')}"
    assert "content" in res and len(res["content"]) > 1000
    assert "debug_file_path" in res
    debug_path = res["debug_file_path"]
    assert debug_path != "", "debug_file_path should not be empty"

    file_obj = Path(debug_path)
    assert file_obj.exists(), f"Debug file {debug_path} should exist on disk"
    assert file_obj.is_file(), f"{debug_path} should be a file"

    content = file_obj.read_text(encoding="utf-8")
    assert f"<!-- Source URL: {url} -->" in content
    assert "<!-- Character Count:" in content


def test_fetch_document_failure_handling():
    """Verify that an invalid or unresolvable URL returns ERROR status and does not write debug files."""
    invalid_url = "https://invalid-non-existent-domain-123456789.com/paper.pdf"
    res = search_tools.fetch_document(invalid_url)

    assert res["status"] == "ERROR"
    assert res["content"] == ""
    assert res["debug_file_path"] == ""
    assert "error" in res

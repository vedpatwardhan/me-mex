from pathlib import Path
from app.tools.search_tools import search_tools


def test_fetch_document_debug_markdown_persistence():
    """Verify SearchTools.fetch_document creates and persists raw extracted markdown in backend/temp_downloads/."""
    url = "https://arxiv.org/abs/2301.00001"
    res = search_tools.fetch_document(url)

    assert "content" in res
    assert "debug_file_path" in res
    debug_path = res["debug_file_path"]
    assert debug_path != "", "debug_file_path should not be empty"

    file_obj = Path(debug_path)
    assert file_obj.exists(), f"Debug file {debug_path} should exist on disk"
    assert file_obj.is_file(), f"{debug_path} should be a file"

    content = file_obj.read_text(encoding="utf-8")
    assert len(content) > 0, "Debug markdown file should not be empty"
    assert f"<!-- Source URL: {url} -->" in content
    assert "<!-- Downloaded At:" in content
    assert "<!-- Character Count:" in content


def test_fetch_document_failure_handling():
    """Verify that an invalid or unresolvable URL returns ERROR status and does not write debug files."""
    invalid_url = "https://invalid-non-existent-domain-123456789.com/paper.pdf"
    res = search_tools.fetch_document(invalid_url)

    assert res["status"] == "ERROR"
    assert res["content"] == ""
    assert res["debug_file_path"] == ""
    assert "error" in res

from pathlib import Path

from app.v2.bootstrap.notes_to_jsonl import _parse_deeper_read, emit_synthetic_rows


def test_parse_deeper_read_minimal(tmp_path):
    p = tmp_path / "deeper_read_notes.md"
    p.write_text("## ERA Paper\nLine one\nLine two\n")
    roots = _parse_deeper_read(p)
    assert len(roots) >= 1
    rows = emit_synthetic_rows(roots)
    if len(roots) >= 2:
        assert rows[0]["query_node"]["node_kind"] == "ROOT"
    else:
        assert rows == []


def test_real_docs_if_present():
    docs = Path(__file__).resolve().parents[5] / "docs" / "deeper_read_notes.md"
    if not docs.exists():
        return
    roots = _parse_deeper_read(docs)
    assert len(roots) > 0

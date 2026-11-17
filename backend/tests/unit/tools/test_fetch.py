from pathlib import Path

from app.db import ToolContext
from app.tools import fetch


def test_fetch_local_file(store, project, tmp_path):
    p = tmp_path / "note.txt"
    p.write_text("Hello normalized fetch fixture.", encoding="utf-8")
    ctx = ToolContext(project_id=project.id, thread_id="f1", store=store)
    out = fetch.fetch_normalized_text(ctx, f"file://{p}")
    assert "Hello normalized" in out["text"]
    assert len(out["content_hash"]) == 16

import json
from pathlib import Path

from app.services.decision_trace_writer import append_decision_trace_row


def test_append_decision_trace_row_disabled(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.config.settings.DECISION_TRACE_DIR", str(tmp_path))
    monkeypatch.setattr("app.config.settings.DECISION_TRACE_ENABLED", False)

    path = append_decision_trace_row("demo", {"scenario": "test"})
    assert path is None


def test_append_decision_trace_row_writes_jsonl(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.config.settings.DECISION_TRACE_DIR", str(tmp_path))
    monkeypatch.setattr("app.config.settings.DECISION_TRACE_ENABLED", True)

    path = append_decision_trace_row(
        "global",
        {
            "scenario": "placement",
            "thread_id": "voice-global",
            "model_relevance_probs": {"a": 0.5, "b": 0.5},
        },
    )
    assert path is not None
    assert path.exists()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["project_id"] == "global"
    assert row["provenance"] == "live_session"
    assert row["scenario"] == "placement"

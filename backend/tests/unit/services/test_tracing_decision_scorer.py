import json
from pathlib import Path

from app.db import ToolContext
from app.services.decision_scorer import MockDecisionScorer, ScorerNode, TracingDecisionScorer
from app.services.decision_trace_context import decision_trace_scope


def test_tracing_scorer_logs_and_appends(monkeypatch, tmp_path: Path, caplog):
    import logging

    caplog.set_level(logging.INFO, logger="memex.v2.decision")
    monkeypatch.setattr("app.config.settings.DECISION_TRACE_DIR", str(tmp_path))
    monkeypatch.setattr("app.config.settings.DECISION_TRACE_ENABLED", True)

    inner = MockDecisionScorer()
    scorer = TracingDecisionScorer(inner)
    query = ScorerNode(id="q", title="Q", node_kind="ROOT")
    front = [
        ScorerNode(id="a", title="A", node_kind="CONCEPT_M"),
        ScorerNode(id="b", title="B", node_kind="CONCEPT_M"),
    ]
    ctx = ToolContext(project_id="p1", thread_id="t1", store=None)  # type: ignore[arg-type]

    with decision_trace_scope(ctx, "placement"):
        probs = scorer.score(query, front)

    assert abs(sum(probs.values()) - 1.0) < 1e-6
    assert any("decision_hop_ms=" in r.message for r in caplog.records)

    files = list((tmp_path / "p1").glob("*.jsonl"))
    assert len(files) == 1
    row = json.loads(files[0].read_text(encoding="utf-8").strip().splitlines()[0])
    assert row["scenario"] == "placement"
    assert "model_relevance_probs" in row

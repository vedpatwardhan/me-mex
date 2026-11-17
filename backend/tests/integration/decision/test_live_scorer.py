import pytest

from app.services.decision_scorer import HttpDecisionScorer, ScorerNode


@pytest.mark.vllm
def test_http_decision_scorer_smoke():
    scorer = HttpDecisionScorer()
    q = ScorerNode(id="q", title="query", node_kind="ROOT")
    front = [
        ScorerNode(id="a", title="A", node_kind="CONCEPT_M"),
        ScorerNode(id="b", title="B", node_kind="CONCEPT_M"),
    ]
    probs = scorer.score(q, front)
    assert set(probs.keys()) == {"a", "b"}
    assert abs(sum(probs.values()) - 1.0) < 0.05

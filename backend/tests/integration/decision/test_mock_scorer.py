from app.v2.services.decision_scorer import MockDecisionScorer, ScorerNode


def test_mock_frontier_keys():
    scorer = MockDecisionScorer()
    q = ScorerNode(id="q", title="q", node_kind="ROOT")
    front = [
        ScorerNode(id=f"f{i}", title=f"n{i}", node_kind="CONCEPT_M") for i in range(3)
    ]
    probs = scorer.score(q, front)
    assert set(probs.keys()) == {f"f{i}" for i in range(3)}

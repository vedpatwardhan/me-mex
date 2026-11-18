from app.services.scoring_text import format_scorer_document, logits_to_relevance_probs


def test_format_scorer_document_includes_kind_and_body():
    text = format_scorer_document(
        {
            "id": "n1",
            "node_kind": "ROOT",
            "title": "Paper X",
            "gist": "Short gist",
        }
    )
    assert "[ROOT] Paper X" in text
    assert "Short gist" in text


def test_format_scorer_document_truncates_long_body():
    long = "x" * 600
    text = format_scorer_document({"title": "T", "description": long})
    assert len(text.split("\n", 1)[-1]) <= 512


def test_logits_to_relevance_probs_sums_to_one():
    probs = logits_to_relevance_probs(["a", "b", "c"], [1.0, 2.0, 0.5])
    assert set(probs.keys()) == {"a", "b", "c"}
    assert abs(sum(probs.values()) - 1.0) < 1e-6
    assert probs["b"] > probs["a"] > probs["c"]
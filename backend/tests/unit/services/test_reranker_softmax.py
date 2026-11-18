import math

from app.services.scoring_text import logits_to_relevance_probs


def test_uniform_when_logits_equal():
    probs = logits_to_relevance_probs(["x", "y"], [0.0, 0.0])
    assert abs(probs["x"] - 0.5) < 1e-6
    assert abs(probs["y"] - 0.5) < 1e-6


def test_single_candidate():
    probs = logits_to_relevance_probs(["only"], [3.14])
    assert probs == {"only": 1.0}


def test_numerical_stability_large_logits():
    probs = logits_to_relevance_probs(["a", "b"], [1000.0, 1000.0 + math.log(2)])
    assert abs(probs["b"] / probs["a"] - 2.0) < 0.01

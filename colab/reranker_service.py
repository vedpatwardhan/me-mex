"""Cross-encoder batch scoring for POST /v1/decision/score."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from scoring_text import format_scorer_document, logits_to_relevance_probs

BGE_RERANKER_MODEL = os.getenv("BGE_RERANKER_MODEL", "BAAI/bge-reranker-base")


@lru_cache(maxsize=1)
def _cross_encoder():
    from sentence_transformers import CrossEncoder

    return CrossEncoder(BGE_RERANKER_MODEL)


def reranker_model_name() -> str:
    return BGE_RERANKER_MODEL


def score_batch(query: dict[str, Any], frontier: list[dict[str, Any]]) -> dict[str, float]:
    if not frontier:
        return {}
    qtext = format_scorer_document(query)
    ids: list[str] = []
    pairs: list[tuple[str, str]] = []
    for n in frontier:
        nid = str(n["id"])
        ids.append(nid)
        pairs.append((qtext, format_scorer_document(n)))
    model = _cross_encoder()
    raw = model.predict(pairs)
    logits = [float(x) for x in raw]
    probs = logits_to_relevance_probs(ids, logits)
    missing = {str(n["id"]) for n in frontier} - set(probs.keys())
    if missing:
        raise ValueError(f"missing frontier ids in reranker output: {missing}")
    return probs
"""DecisionScorer client + mock for Phase 1."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Protocol

import httpx
from app.config import settings
from app.services.decision_trace_context import get_decision_trace_context
from app.services.decision_trace_writer import (
    append_decision_trace_row,
    frontier_from_scorer_nodes,
    query_node_dict,
)

logger = logging.getLogger("memex.v2.decision")


@dataclass
class ScorerNode:
    id: str
    title: str
    node_kind: str
    gist: str = ""
    description: str = ""


class DecisionScorerProtocol(Protocol):
    def score(self, query_node: ScorerNode, frontier: list[ScorerNode]) -> dict[str, float]: ...


class MockDecisionScorer:
    """Uniform decay scores for tests — keys cover 100% of frontier."""

    def score(self, query_node: ScorerNode, frontier: list[ScorerNode]) -> dict[str, float]:
        if not frontier:
            return {}
        base = 1.0 / len(frontier)
        return {n.id: base for n in frontier}


class HttpDecisionScorer:
    """POST to Colab gateway cross-encoder reranker (pytest -m vllm)."""

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.colab_vllm_api_base).rstrip("/")

    def score(self, query_node: ScorerNode, frontier: list[ScorerNode]) -> dict[str, float]:
        payload = {
            "query_node": query_node.__dict__,
            "frontier": [n.__dict__ for n in frontier],
        }
        with httpx.Client(timeout=60.0) as client:
            r = client.post(f"{self.base_url}/decision/score", json=payload)
            r.raise_for_status()
            data = r.json()
        probs: dict[str, float] = data.get("relevance_probs", {})
        missing = {n.id for n in frontier} - set(probs.keys())
        if missing:
            raise ValueError(f"DecisionScorer missing frontier ids: {missing}")
        return probs


class TracingDecisionScorer:
    """Latency logging + optional live JSONL traces."""

    def __init__(self, inner: DecisionScorerProtocol):
        self._inner = inner

    def score(self, query_node: ScorerNode, frontier: list[ScorerNode]) -> dict[str, float]:
        meta = get_decision_trace_context()
        scenario = meta.scenario if meta else "unknown"
        start = time.perf_counter()
        probs = self._inner.score(query_node, frontier)
        ms = (time.perf_counter() - start) * 1000
        logger.info(
            "decision_hop_ms=%.2f scenario=%s frontier_n=%d project_id=%s thread_id=%s",
            ms,
            scenario,
            len(frontier),
            meta.project_id if meta else "",
            meta.thread_id if meta else "",
        )
        if meta and settings.DECISION_TRACE_ENABLED and frontier:
            append_decision_trace_row(
                meta.project_id,
                {
                    "scenario": meta.scenario,
                    "thread_id": meta.thread_id,
                    "approval_id": meta.approval_id,
                    "query_node": query_node_dict(query_node),
                    "frontier": frontier_from_scorer_nodes(frontier),
                    "model_relevance_probs": probs,
                },
            )
        return probs


_scorer_override: DecisionScorerProtocol | None = None


def set_decision_scorer_override(scorer: DecisionScorerProtocol | None) -> None:
    global _scorer_override
    _scorer_override = scorer


def get_decision_scorer() -> DecisionScorerProtocol:
    if _scorer_override is not None:
        return _scorer_override
    inner: DecisionScorerProtocol
    if settings.DECISION_SCORER_MODE == "live":
        inner = HttpDecisionScorer()
    else:
        inner = MockDecisionScorer()
    return TracingDecisionScorer(inner)

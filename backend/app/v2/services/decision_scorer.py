"""DecisionScorer client + mock for Phase 1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.config import settings


@dataclass
class ScorerNode:
    id: str
    title: str
    node_kind: str
    gist: str = ""


class DecisionScorerProtocol(Protocol):
    def score(
        self, query_node: ScorerNode, frontier: list[ScorerNode]
    ) -> dict[str, float]:
        ...


class MockDecisionScorer:
    """Uniform decay scores for tests — keys cover 100% of frontier."""

    def score(
        self, query_node: ScorerNode, frontier: list[ScorerNode]
    ) -> dict[str, float]:
        if not frontier:
            return {}
        base = 1.0 / len(frontier)
        return {n.id: base for n in frontier}


class HttpDecisionScorer:
    """POST to Colab vLLM LoRA adapter (optional manual -m vllm)."""

    def __init__(self, base_url: str | None = None, adapter_id: str | None = None):
        self.base_url = (base_url or settings.COLAB_VLLM_URL).rstrip("/")
        self.adapter_id = adapter_id or settings.LORA_ADAPTER_ID

    def score(
        self, query_node: ScorerNode, frontier: list[ScorerNode]
    ) -> dict[str, float]:
        payload = {
            "query_node": query_node.__dict__,
            "frontier": [n.__dict__ for n in frontier],
            "adapter_id": self.adapter_id,
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


_default_scorer: DecisionScorerProtocol = MockDecisionScorer()


def get_decision_scorer(live: bool = False) -> DecisionScorerProtocol:
    if live:
        return HttpDecisionScorer()
    return _default_scorer

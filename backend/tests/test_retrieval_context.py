"""Offline tests for retrieval subgraph closure and context formatting."""

import os
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import pytest
from app.db import db_engine
from app.models import GraphEdge, GraphNode
from app.models import RetrievalRelevanceItem, RetrievalRelevancePayload
from app.services.retrieval_context import (
    collect_retrieval_subgraph,
    filter_retrieval_finding_by_relevance,
    format_retrieval_graph_context,
)


@pytest.fixture
def retrieval_closure_graph():
    project_id = "proj_retrieval_closure"
    genesis = GraphNode(
        _id="concept_genesis",
        node_type="CONCEPT",
        title="Everything",
        description="Scope",
        project_ids=[project_id],
        metadata={"is_genesis": True, "immutable": False},
    )
    hub = GraphNode(
        _id="hub_mut",
        node_type="CONCEPT",
        title="Domain Hub",
        description="Mutable hub",
        project_ids=[project_id],
        metadata={"immutable": False, "mutable_parent_id": "concept_genesis"},
    )
    root = GraphNode(
        _id="paper_root",
        node_type="ROOT",
        title="Paper A",
        description="Root summary",
        project_ids=[project_id],
        metadata={"immutable": True},
    )
    imm = GraphNode(
        _id="imm_evidence",
        node_type="CONCEPT",
        title="Factual Claim",
        description="Immutable evidence",
        project_ids=[project_id],
        metadata={"immutable": True, "root_node_id": "paper_root"},
    )
    for n in (genesis, hub, root, imm):
        db_engine.upsert_node(n)
    db_engine.upsert_edge(
        GraphEdge(
            _id="e_hub_genesis",
            source_id="hub_mut",
            target_id="concept_genesis",
            description="SUBSET_OF",
            project_ids=[project_id],
        )
    )
    db_engine.upsert_edge(
        GraphEdge(
            _id="e_hub_imm",
            source_id="hub_mut",
            target_id="imm_evidence",
            description="RELEVANT_TO",
            project_ids=[project_id],
        )
    )
    return project_id, genesis, hub, imm, root


def test_collect_retrieval_subgraph_includes_immutable_and_root(
    retrieval_closure_graph,
):
    project_id, genesis, hub, imm, root = retrieval_closure_graph
    explored = [genesis, hub]
    result = collect_retrieval_subgraph(explored, project_id)

    imm_ids = {r["id"] for r in result["immutable_evidence_nodes"]}
    root_ids = {r["id"] for r in result["root_provenance_nodes"]}
    assert "imm_evidence" in imm_ids
    assert "paper_root" in root_ids
    assert "hub_mut" in {r["id"] for r in result["mutable_context_nodes"]}
    assert "imm_evidence" in result["context_node_ids"]


def test_format_retrieval_graph_context_contains_titles(retrieval_closure_graph):
    project_id, genesis, hub, imm, root = retrieval_closure_graph
    finding = collect_retrieval_subgraph([genesis, hub], project_id)
    text = format_retrieval_graph_context(
        finding, genesis_description="Genesis scope text"
    )
    assert "Factual Claim" in text
    assert "Domain Hub" in text
    assert "Paper A" in text
    assert "Genesis scope text" in text


@pytest.mark.asyncio
async def test_execute_retrieval_flow_injects_graph_context(monkeypatch):
    """Retrieval finale must pass assembled subgraph into conversation LLM messages."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.agents.orchestrator import ExecutiveOrchestrator
    from app.models import GraphNode

    orch = ExecutiveOrchestrator()
    captured_messages = []

    fake_finding = {
        "emitted_events": [],
        "traversed_node_ids": ["concept_genesis", "hub_mut"],
        "mutable_context_nodes": [
            {
                "id": "hub_mut",
                "title": "Domain Hub",
                "description": "Mutable hub",
                "immutable": False,
            }
        ],
        "immutable_evidence_nodes": [
            {
                "id": "imm_evidence",
                "title": "Factual Claim",
                "description": "Evidence",
                "immutable": True,
            }
        ],
        "root_provenance_nodes": [],
        "context_node_ids": ["hub_mut", "imm_evidence"],
    }

    async def fake_stream(messages, max_tokens=512, caller=""):
        captured_messages.extend(messages)
        yield "Answer grounded in graph."

    monkeypatch.setattr(
        orch.llm,
        "stream_chat_completion",
        fake_stream,
    )

    mock_nav = MagicMock()
    mock_nav.navigator_id = "nav_test"
    mock_nav.genesis_node = GraphNode(
        _id="concept_genesis",
        node_type="CONCEPT",
        title="Everything",
        description="Scope",
    )
    mock_nav.explore_for_retrieval = MagicMock(return_value=fake_finding)

    monkeypatch.setattr(
        "app.agents.orchestrator.filter_retrieval_finding_by_relevance",
        lambda query, finding, **kw: {
            **finding,
            "answer_scope": "Decision models only.",
        },
    )

    with patch("app.agents.orchestrator.GraphNavigator", return_value=mock_nav):
        events = []
        async for evt in orch.execute_retrieval_flow(
            "What does the graph say?",
            [],
            project_id="proj_retrieval_closure",
        ):
            events.append(evt)

    assert any(e.get("event") == "retrieval_summary" for e in events)
    assert any(e.get("event") == "chat_complete" for e in events)
    assert captured_messages
    system_content = next(
        m["content"] for m in captured_messages if m.get("role") == "system"
    )
    assert "Factual Claim" in system_content
    assert "Filtered graph context" in system_content
    assert "Decision models only" in system_content


def test_filter_retrieval_finding_keeps_selected_only(monkeypatch):
    finding = {
        "mutable_context_nodes": [
            {"id": "hub_decision", "title": "Decision Models", "description": "DM"},
            {"id": "hub_world", "title": "World Models", "description": "WM"},
        ],
        "immutable_evidence_nodes": [
            {
                "id": "imm_dm",
                "title": "PRM steps",
                "description": "",
                "immutable": True,
            },
        ],
        "root_provenance_nodes": [],
        "context_node_ids": ["hub_decision", "hub_world", "imm_dm"],
    }

    def mock_llm(messages, response_model, **kwargs):
        assert response_model is RetrievalRelevancePayload
        return RetrievalRelevancePayload(
            selected_concepts=[
                RetrievalRelevanceItem(concept_index=1, rationale="Query is about DM"),
                RetrievalRelevanceItem(concept_index=3, rationale="DM evidence"),
            ],
            answer_scope="Only decision-model papers; omit world models.",
        )

    monkeypatch.setattr(
        "app.services.retrieval_context.llm_gateway.generate_structured_completion",
        mock_llm,
    )

    out = filter_retrieval_finding_by_relevance(
        "How do decision models verify steps?", finding
    )
    titles = {r["title"] for r in out["mutable_context_nodes"]}
    assert titles == {"Decision Models"}
    assert out["immutable_evidence_nodes"][0]["id"] == "imm_dm"
    assert (
        "world" in out["answer_scope"].lower()
        or "decision" in out["answer_scope"].lower()
    )


def test_explore_for_retrieval_merges_closure(retrieval_closure_graph, monkeypatch):
    """explore_for_retrieval uses retrieval traversal prompt and merges evidence closure."""
    from app.agents.graph_navigator import GraphNavigator

    project_id, genesis, hub, imm, root = retrieval_closure_graph
    agent = GraphNavigator(project_id)
    seen: dict = {}

    def stub_traverse(self, **kwargs):
        seen.update(kwargs)
        return {
            "explored_nodes": [genesis, hub],
            "traversed_node_ids": [genesis.id, hub.id],
            "emitted_events": [],
            "department_id": agent.department_id,
            "department_name": agent.department_name,
            "genesis_node_id": genesis.id,
        }

    monkeypatch.setattr(
        GraphNavigator,
        "traverse_mutable_tree_from_genesis",
        stub_traverse,
    )
    out = agent.explore_for_retrieval("query", project_id=project_id)
    assert seen.get("traversal_prompt") == "graph_tree_traversal_retrieval"
    assert "imm_evidence" in out["context_node_ids"]
    assert "paper_root" in out["context_node_ids"]

import pytest
import json
from app.db import db_engine
from app.models import GraphNode, GraphEdge
from app.agents.orchestrator import orchestrator


@pytest.mark.asyncio
async def test_generalize_affected_target_nodes(monkeypatch):
    """Verify that _generalize_affected_target_nodes updates mutable target nodes to accommodate new concepts."""
    project_id = "proj_test_generalize_pass"

    # Setup 1 normal mutable node and 1 primordial Everything node
    normal_target = GraphNode(
        _id="concept_target_normal",
        node_type="CONCEPT",
        title="Predictive Models",
        description="Specific models predicting trajectory states.",
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    everything_target = GraphNode(
        _id="concept_genesis",
        node_type="CONCEPT",
        title="Everything",
        description="Primordial knowledge anchor.",
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    new_child_1 = GraphNode(
        _id="concept_new_child_1",
        node_type="CONCEPT",
        title="Multimodal Diffusion",
        description="Diffusion models for video generation.",
        project_ids=[project_id],
        metadata={"immutable": True},
    )
    new_child_2 = GraphNode(
        _id="concept_new_child_2",
        node_type="CONCEPT",
        title="Quantum Computing Notes",
        description="Foundational principles of quantum states.",
        project_ids=[project_id],
        metadata={"immutable": True},
    )

    db_engine.upsert_node(normal_target)
    db_engine.upsert_node(everything_target)
    db_engine.upsert_node(new_child_1)
    db_engine.upsert_node(new_child_2)

    db_engine.upsert_edge(
        GraphEdge(
            _id="edge_1",
            source_id="concept_new_child_1",
            target_id="concept_target_normal",
            description="RELEVANT_TO",
            project_ids=[project_id],
        )
    )
    db_engine.upsert_edge(
        GraphEdge(
            _id="edge_2",
            source_id="concept_new_child_2",
            target_id="concept_genesis",
            description="RELEVANT_TO",
            project_ids=[project_id],
        )
    )

    # Mock LLM generation for generalization
    def mock_chat_completion(messages, **kwargs):
        return json.dumps(
            {
                "generalizations": [
                    {
                        "node_index": 1,
                        "updated_title": "Predictive & Generative World Models",
                        "updated_description": "Broadened scope encompassing predictive trajectory planning and multimodal diffusion.",
                    },
                    {
                        "node_index": 2,
                        "updated_title": "Arbitrary New Title To Be Ignored",
                        "updated_description": "Expanded universal genesis anchor accommodating quantum computing and multimodal foundations.",
                    },
                ]
            }
        )

    from app.services.llm_gateway import llm_gateway

    monkeypatch.setattr(llm_gateway, "generate_chat_completion", mock_chat_completion)

    events = []
    async for evt in orchestrator._generalize_affected_target_nodes(
        mutable_targets=[normal_target, everything_target],
        project_id=project_id,
    ):
        events.append(evt)

    # Check updated normal target
    updated_normal = db_engine.get_node("concept_target_normal")
    assert updated_normal.title == "Predictive & Generative World Models"
    assert "multimodal diffusion" in updated_normal.description.lower()

    # Check updated Everything target: title MUST remain 'Everything'
    updated_everything = db_engine.get_node("concept_genesis")
    assert updated_everything.title == "Everything"
    assert "quantum computing" in updated_everything.description.lower()

    # Verify telemetry events emitted
    assert len(events) == 2
    assert any("Predictive & Generative World Models" in e["message"] for e in events)
    assert any("Everything" in e["message"] for e in events)

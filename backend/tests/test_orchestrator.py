"""
Test Suite: Executive Orchestrator Intent Classification & Workflow Routing

Aligned with docs/ARCHITECTURE.md Section 2:
- Validates classification into 3 execution paths (`CONVERSATION`, `RETRIEVAL`, `INGESTION`).
- Validates path intent decoding context awareness across chat history.
"""

import pytest
from app.agents.orchestrator import orchestrator
from app.services.llm_gateway import llm_gateway

pytestmark = pytest.mark.xdist_group(name="worker1")


@pytest.mark.vllm
def test_classify_intent_conversation():
    """Verify CONVERSATION path classification for greetings and basic prompts."""
    if not llm_gateway.is_server_available():
        print("  ⏭️ test_classify_intent_conversation [SKIPPED - vLLM Server Offline]")
        return
    res = orchestrator.classify_intent("Hello, good morning!", chat_history=[])
    assert res["intent"] == "CONVERSATION"
    assert res["doc_type"] is None
    assert res["source_url"] is None
    assert res["raw_text"] is None


@pytest.mark.vllm
def test_classify_intent_retrieval():
    """Verify RETRIEVAL path classification for concept research queries."""
    if not llm_gateway.is_server_available():
        print("  ⏭️ test_classify_intent_retrieval [SKIPPED - vLLM Server Offline]")
        return
    res = orchestrator.classify_intent(
        "Explain latent world models vs pixel world models", chat_history=[]
    )
    assert res["intent"] == "RETRIEVAL"
    assert res["doc_type"] is None
    assert res["source_url"] is None
    assert res["raw_text"] is None


@pytest.mark.vllm
def test_classify_intent_ingestion():
    """Verify INGESTION path classification for paper links and text pastes."""
    if not llm_gateway.is_server_available():
        print("  ⏭️ test_classify_intent_ingestion [SKIPPED - vLLM Server Offline]")
        return
    res = orchestrator.classify_intent(
        "https://arxiv.org/pdf/2605.11550 paper abstract", chat_history=[]
    )
    assert res["intent"] == "INGESTION"
    assert res["doc_type"] in ("paper", "blog", "post")


@pytest.mark.vllm
def test_classify_intent_with_chat_history():
    """Verify chat_history context influences follow-up intent classification."""
    if not llm_gateway.is_server_available():
        print(
            "  ⏭️ test_classify_intent_with_chat_history [SKIPPED - vLLM Server Offline]"
        )
        return
    history = [
        {"role": "user", "text": "What is model predictive control?"},
        {
            "role": "agent",
            "text": "MPC optimizes control inputs over predicted state rollouts.",
        },
    ]
    res = orchestrator.classify_intent(
        "Compare this with diffusion policies", chat_history=history
    )
    assert res["intent"] == "RETRIEVAL"
    assert res["doc_type"] is None
    assert res["source_url"] is None
    assert res["raw_text"] is None


@pytest.mark.vllm
def test_classify_intent_dual_payload():
    """Verify dual payload extraction when both URL and commentary notes are provided together."""
    if not llm_gateway.is_server_available():
        print("  ⏭️ test_classify_intent_dual_payload [SKIPPED - vLLM Server Offline]")
        return
    res = orchestrator.classify_intent(
        "Include this document https://arxiv.org/pdf/2605.11550 because it proposes a novel skeletal loss formulation.",
        chat_history=[],
    )
    assert res["intent"] == "INGESTION"
    assert res["doc_type"] == "paper"
    assert res["source_url"] == "https://arxiv.org/pdf/2605.11550"


def test_consolidate_extracted_concepts():
    """Verify empty raw concepts handling in consolidate_extracted_concepts."""
    res = orchestrator.consolidate_extracted_concepts(
        raw_extracted_concepts=[],
        doc_title="Test Document",
        query="Test query",
        chat_history=[],
    )
    assert res["concepts"] == []


@pytest.mark.vllm
def test_consolidate_extracted_concepts_with_payload():
    """Verify concept consolidation deduplication and passage ID preservation with non-empty payload."""
    if not llm_gateway.is_server_available():
        print(
            "  ⏭️ test_consolidate_extracted_concepts_with_payload [SKIPPED - vLLM Server Offline]"
        )
        return

    raw_concepts = [
        {
            "idx": 0,
            "title": "Latent World Model",
            "description": "Learns compact representations of high-dimensional observations to predict future state transitions.",
            "passage_ids": ["pass_01"],
        },
        {
            "idx": 1,
            "title": "Latent-Space Dynamics",
            "description": "Predicts forward state dynamics entirely within the compact latent embedding space.",
            "passage_ids": ["pass_02"],
        },
        {
            "idx": 2,
            "title": "Monte Carlo Tree Search",
            "description": "Heuristic search algorithm for decision processes that balances exploration and exploitation.",
            "passage_ids": ["pass_01", "pass_03"],
        },
        {
            "idx": 3,
            "title": "MCTS Action Planning",
            "description": "Uses Monte Carlo rollouts within the world model to select high-reward actions.",
            "passage_ids": ["pass_03"],
        },
        {
            "idx": 4,
            "title": "Process Reward Model",
            "description": "Evaluates intermediate reasoning and action steps to provide dense credit assignment.",
            "passage_ids": ["pass_02"],
        },
    ]

    res = orchestrator.consolidate_extracted_concepts(
        raw_extracted_concepts=raw_concepts,
        doc_title="World Models and Search Planning",
        query="Explain how latent world models combine with tree search planning",
        chat_history=[],
    )

    concepts = res.get("concepts", [])

    # Verify canonical deduplication occurred and output lies in expected range
    assert (
        2 <= len(concepts) <= 5
    ), f"Expected 2-5 consolidated concepts, got {len(concepts)}"
    assert res.get("doc_description") and isinstance(res["doc_description"], str)

    # Verify concept properties and passage_id preservation
    all_assigned_passages = set()
    for c in concepts:
        assert "title" in c and c["title"].strip()
        assert "description" in c and c["description"].strip()
        assert "passage_ids" in c and isinstance(c["passage_ids"], list)
        all_assigned_passages.update(c["passage_ids"])

    # Ensure originating passage IDs were preserved (zero data loss)
    for p_id in ["pass_01", "pass_02", "pass_03"]:
        assert (
            p_id in all_assigned_passages
        ), f"Passage {p_id} lost during consolidation"

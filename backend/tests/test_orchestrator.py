"""
Test Suite: Executive Orchestrator Intent Classification & Workflow Routing

Aligned with docs/ARCHITECTURE.md Section 2:
- Validates classification into 3 execution paths (`CONVERSATION`, `RETRIEVAL`, `INGESTION`).
- Validates path intent decoding context awareness across chat history.
"""

from app.agents.orchestrator import orchestrator


def test_classify_intent_conversation():
    """Verify CONVERSATION path classification for greetings and basic prompts."""
    res = orchestrator.classify_intent("Hello, good morning!", chat_history=[])
    assert res["intent"] == "CONVERSATION"


def test_classify_intent_retrieval():
    """Verify RETRIEVAL path classification for concept research queries."""
    res = orchestrator.classify_intent(
        "Explain latent world models vs pixel world models", chat_history=[]
    )
    assert res["intent"] == "RETRIEVAL"


def test_classify_intent_ingestion():
    """Verify INGESTION path classification for paper links and text pastes."""
    res = orchestrator.classify_intent(
        "https://arxiv.org/abs/2401.12345 paper abstract", chat_history=[]
    )
    assert res["intent"] == "INGESTION"


def test_classify_intent_with_chat_history():
    """Verify chat_history context influences follow-up intent classification."""
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


def test_consolidate_extracted_concepts():
    """Verify empty raw concepts handling in consolidate_extracted_concepts."""
    res = orchestrator.consolidate_extracted_concepts(
        raw_extracted_concepts=[],
        extracted_relations=[],
        doc_title="Test Document",
        query="Test query",
        chat_history=[],
    )
    assert res["concepts"] == []
    assert res["relations"] == []

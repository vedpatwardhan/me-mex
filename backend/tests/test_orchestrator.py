"""
Test Suite: Executive Orchestrator Intent Classification & Workflow Routing

Aligned with docs/ARCHITECTURE.md Section 2:
- Validates classification into 3 execution paths (`CONVERSATION`, `RETRIEVAL`, `INGESTION`).
- Validates path intent decoding context awareness across chat history.
"""

from app.agents.orchestrator import orchestrator
from app.services.llm_gateway import llm_gateway


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


def test_classify_intent_dual_payload():
    """Verify dual payload extraction when both URL and commentary notes are provided together."""
    if not llm_gateway.is_server_available():
        print("  ⏭️ test_classify_intent_dual_payload [SKIPPED - vLLM Server Offline]")
        return
    res = orchestrator.classify_intent(
        "Include this document https://arxiv.org/abs/2605.11550 because it proposes a novel skeletal loss formulation.",
        chat_history=[],
    )
    assert res["intent"] == "INGESTION"
    assert res["doc_type"] == "paper"
    assert res["source_url"] is not None
    assert "arxiv.org" in res["source_url"]


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

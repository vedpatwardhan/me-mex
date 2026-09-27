from app.agents.orchestrator import orchestrator


from app.agents.orchestrator import orchestrator


def test_classify_intent_direct():
    """Verify DIRECT_CONVERSATION classification for greetings and basic prompts."""
    res = orchestrator.classify_intent("Hello, good morning!", chat_history=[])
    assert res["intent"] == "DIRECT_CONVERSATION"


def test_classify_intent_retrieval():
    """Verify GRAPH_RETRIEVAL classification for concept research queries."""
    res = orchestrator.classify_intent(
        "Explain latent world models vs pixel world models", chat_history=[]
    )
    assert res["intent"] == "GRAPH_RETRIEVAL"


def test_classify_intent_ingestion():
    """Verify DOCUMENT_INGESTION classification for arXiv paper links and text pastes."""
    res = orchestrator.classify_intent(
        "https://arxiv.org/abs/2401.12345 paper abstract", chat_history=[]
    )
    assert res["intent"] == "DOCUMENT_INGESTION"


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
    assert res["intent"] == "GRAPH_RETRIEVAL"

from app.agents.orchestrator import orchestrator


def test_classify_intent_direct():
    """Verify DIRECT_CONVERSATION classification for greetings and basic prompts."""
    intent = orchestrator.classify_intent("Hello, good morning!")
    assert intent == "DIRECT_CONVERSATION"


def test_classify_intent_retrieval():
    """Verify GRAPH_RETRIEVAL classification for concept research queries."""
    intent = orchestrator.classify_intent(
        "Explain latent world models vs pixel world models"
    )
    assert intent == "GRAPH_RETRIEVAL"


def test_classify_intent_ingestion():
    """Verify DOCUMENT_INGESTION classification for arXiv paper links and text pastes."""
    intent = orchestrator.classify_intent(
        "https://arxiv.org/abs/2401.12345 paper abstract"
    )
    assert intent == "DOCUMENT_INGESTION"


def test_classify_intent_with_chat_history():
    """Verify chat_history context influences follow-up intent classification."""
    history = [
        {"role": "user", "text": "What is model predictive control?"},
        {
            "role": "agent",
            "text": "MPC optimizes control inputs over predicted state rollouts.",
        },
    ]
    followup_intent = orchestrator.classify_intent(
        "Compare this with diffusion policies", chat_history=history
    )
    assert followup_intent == "GRAPH_RETRIEVAL"


def test_extract_document_title():
    """Verify document title extraction produces a non-empty string."""
    raw_text = "LeWM introduces Latent Efficient World Models for trajectory optimization in high-dimensional state space."
    title = orchestrator._extract_document_title(raw_text)
    assert isinstance(title, str)
    assert len(title) > 0

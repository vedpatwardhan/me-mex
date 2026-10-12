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


def test_chunk_text_empty_and_short():
    """Verify empty text returns empty list, and tiny snippet returns single chunk."""
    assert orchestrator._chunk_text("") == []
    short_snippet = "A brief paragraph introducing world models."
    chunks = orchestrator._chunk_text(short_snippet)
    assert len(chunks) == 1
    assert chunks[0] == short_snippet


def test_chunk_text_min_chunks_guarantee():
    """Verify medium-sized text (~15,000 chars) produces at least 5 chunks and strictly <= 30."""
    para = (
        "Latent world models learn state transitions across compact latent embeddings. "
        * 15
    )
    doc_text = "\n\n".join([f"Section {i}\n{para}" for i in range(12)])
    assert len(doc_text) >= 12000

    chunks = orchestrator._chunk_text(doc_text)
    assert 5 <= len(chunks) <= 30
    assert all(len(c.strip()) > 0 for c in chunks)


def test_chunk_text_25_page_paper():
    """Verify a 25-page academic paper (~66,000 chars) yields between 7 and 12 chunks."""
    section = (
        "We formulate the policy optimization objective over simulated latent rollouts. "
        "The dynamics predictor estimates future embeddings conditioned on candidate action sequences. "
        "Heuristic tree search samples action branches to maximize cumulative discounted rewards.\n\n"
        * 5
    )
    # Generate ~66,000 characters
    doc_text = "\n\n".join([f"### Section {i}\n{section}" for i in range(50)])
    assert 60000 <= len(doc_text) <= 75000

    chunks = orchestrator._chunk_text(doc_text)
    assert 7 <= len(chunks) <= 12
    assert all(len(c.strip()) > 0 for c in chunks)


def test_chunk_text_150_page_paper_max_chunks_guarantee():
    """Verify a 150-page document (~350,000 chars) scales up to exactly 30 chunks and NEVER exceeds 30."""
    long_section = (
        "Diffusion policies represent complex multi-modal distributions over continuous action spaces. "
        "By applying denoising diffusion probabilistic models, the agent generates trajectory rollouts. "
        "Residual energy models steer the sampling trajectory toward high-feasibility regions.\n\n"
        * 10
    )
    # Generate ~350,000 characters
    doc_text = "\n\n".join([f"## Chapter {i}\n{long_section}" for i in range(120)])
    assert len(doc_text) >= 300000

    chunks = orchestrator._chunk_text(doc_text)
    assert (
        len(chunks) == 30
    ), f"Expected exactly 30 chunks for massive document, got {len(chunks)}"
    assert all(len(c.strip()) > 0 for c in chunks)


def test_chunk_text_safe_token_ceiling():
    """Verify individual chunk sizes never exceed 45,000 characters to stay within 16k context window."""
    long_para = "A" * 50000
    doc_text = f"{long_para}\n\n{long_para}"
    chunks = orchestrator._chunk_text(doc_text)
    assert 5 <= len(chunks) <= 30
    assert all(len(c) <= 45000 for c in chunks)


def test_extract_markdown_title():
    """Verify document title is extracted from the first true markdown header, ignoring comments and notes."""
    # 1. Simple header
    md1 = "# Attention Is All You Need\n\nVaswani et al."
    assert orchestrator._extract_markdown_title(md1) == "Attention Is All You Need"

    # 2. Markdown with comments and subheader
    md2 = "<!-- Downloaded At: 2026-10-12 -->\n\n## Deep World Models\n\nBody text"
    assert orchestrator._extract_markdown_title(md2) == "Deep World Models"

    # 3. Combined user notes and document content
    md3 = (
        "### User Context & Notes\n"
        "Here are my private notes.\n\n"
        "### Document Content\n"
        "# Accelerating Scientific Discovery with Co-Scientist\n\n"
        "Abstract..."
    )
    assert (
        orchestrator._extract_markdown_title(md3)
        == "Accelerating Scientific Discovery with Co-Scientist"
    )

    # 4. Empty or header-less markdown
    assert orchestrator._extract_markdown_title("") is None
    assert (
        orchestrator._extract_markdown_title("Just plain paragraph without headers")
        is None
    )


def test_search_tools_is_misleading_filename():
    """Verify search_tools rejects local filenames, drafts, and bracketed tags as titles."""
    from app.tools.search_tools import search_tools

    assert search_tools._is_misleading_filename("[CoS] Nature revision AAP") is True
    assert search_tools._is_misleading_filename("main.pdf") is True
    assert search_tools._is_misleading_filename("paper_draft_v2.docx") is True
    assert search_tools._is_misleading_filename("untitled.tex") is True
    assert (
        search_tools._is_misleading_filename(
            "The DAWN of World-Action Interactive Models"
        )
        is False
    )

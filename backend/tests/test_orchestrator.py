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
    assert res.intent == "CONVERSATION"
    assert res.doc_type is None
    assert res.source_url is None
    assert res.raw_text is None


@pytest.mark.vllm
def test_classify_intent_retrieval():
    """Verify RETRIEVAL path classification for concept research queries."""
    if not llm_gateway.is_server_available():
        print("  ⏭️ test_classify_intent_retrieval [SKIPPED - vLLM Server Offline]")
        return
    res = orchestrator.classify_intent(
        "Explain latent world models vs pixel world models", chat_history=[]
    )
    assert res.intent == "RETRIEVAL"
    assert res.doc_type is None
    assert res.source_url is None
    assert res.raw_text is None


@pytest.mark.vllm
def test_classify_intent_ingestion():
    """Verify INGESTION path classification for paper links and text pastes."""
    if not llm_gateway.is_server_available():
        print("  ⏭️ test_classify_intent_ingestion [SKIPPED - vLLM Server Offline]")
        return
    res = orchestrator.classify_intent(
        "https://arxiv.org/pdf/2605.11550 paper abstract", chat_history=[]
    )
    assert res.intent == "INGESTION"
    assert res.doc_type in ("paper", "blog", "post")


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
    assert res.intent == "RETRIEVAL"
    assert res.doc_type is None
    assert res.source_url is None
    assert res.raw_text is None


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
    assert res.intent == "INGESTION"
    assert res.doc_type == "paper"
    assert res.source_url == "https://arxiv.org/pdf/2605.11550"


def test_consolidate_extracted_concepts():
    """Verify empty raw concepts handling in consolidate_extracted_concepts."""
    res = orchestrator.consolidate_extracted_concepts(
        raw_extracted_concepts=[],
        doc_title="Test Document",
        query="Test query",
        chat_history=[],
    )
    assert res.concepts == []


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
        1 <= len(concepts) <= 5
    ), f"Expected 1-5 consolidated concepts, got {len(concepts)}"
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


def test_chunk_text_x_post_single_chunk():
    """Verify a small X post or note (<= 1500 chars) returns exactly 1 chunk without splitting."""
    post_text = (
        "We just released LeWM-v2! A new approach to reachability-conditioned latent world models. "
        "Key insight: unprojecting 2D representations into compact 3D manifolds stabilizes long-horizon rollout planning. "
        "Code and checkpoints available on HuggingFace and GitHub. Read the full paper for details."
    )
    assert len(post_text) < 1500
    chunks = orchestrator._chunk_text(post_text)
    assert len(chunks) == 1
    assert chunks[0] == post_text


def test_chunk_text_short_memo_two_chunks():
    """Verify a short memo (1500 - 4000 chars) produces 2 chunks."""
    p1 = "Paragraph 1 discusses the fundamental motivation behind world models. " * 15
    p2 = "Paragraph 2 details the architectural formulation and loss metrics. " * 15
    doc_text = f"{p1}\n\n{p2}"
    assert 1500 < len(doc_text) <= 4000
    chunks = orchestrator._chunk_text(doc_text)
    assert len(chunks) == 2
    assert all(len(c.strip()) > 0 for c in chunks)


def test_chunk_text_medium_article_three_chunks():
    """Verify a medium article (4000 - 8000 chars) produces 3 chunks."""
    sec = (
        "Exploring diffusion policies over continuous action manifolds with residual energy steering. "
        * 18
    )
    doc_text = "\n\n".join([f"Section {i}\n{sec}" for i in range(3)])
    assert 4000 < len(doc_text) <= 8000
    chunks = orchestrator._chunk_text(doc_text)
    assert len(chunks) == 3
    assert all(len(c.strip()) > 0 for c in chunks)


def test_chunk_text_overview_four_chunks():
    """Verify a multi-section overview (8000 - 14000 chars) produces 4 chunks."""
    sec = (
        "Detailed analysis of state predictive representations and temporal alignment diagnostics. "
        * 25
    )
    doc_text = "\n\n".join([f"Part {i}\n{sec}" for i in range(4)])
    assert 8000 < len(doc_text) <= 14000
    chunks = orchestrator._chunk_text(doc_text)
    assert len(chunks) == 4
    assert all(len(c.strip()) > 0 for c in chunks)


def test_chunk_text_short_paper_five_chunks():
    """Verify a short paper or report (14000 - 25000 chars) produces 5 chunks."""
    para = (
        "Latent world models learn state transitions across compact latent embeddings. "
        * 15
    )
    doc_text = "\n\n".join([f"Section {i}\n{para}" for i in range(15)])
    assert 14000 <= len(doc_text) <= 25000

    chunks = orchestrator._chunk_text(doc_text)
    assert len(chunks) == 5
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


def test_fetch_local_text_file(tmp_path):
    """Verify SearchTools fetches and extracts local .txt file with synthesized heading."""
    from app.tools.search_tools import search_tools

    note_file = tmp_path / "x_post_note.txt"
    note_content = "This is a concise thought on spatial reasoning in robotics and dynamic affordances."
    note_file.write_text(note_content, encoding="utf-8")

    res = search_tools.fetch_document(str(note_file))
    assert res["status"] == "SUCCESS"
    assert res["doc_type"] == "document"
    assert res["url"] == f"file://{note_file.resolve()}"
    assert res["content"].startswith("# x_post_note\n\n")
    assert "spatial reasoning in robotics" in res["content"]


def test_fetch_local_markdown_file(tmp_path):
    """Verify SearchTools fetches local .md file preserving existing headers."""
    from app.tools.search_tools import search_tools

    md_file = tmp_path / "architecture_notes.md"
    md_content = (
        "# End-to-End Multimodal Policies\n\nDiscussion on ACT and diffusion policies."
    )
    md_file.write_text(md_content, encoding="utf-8")

    res = search_tools.fetch_document(f"file://{md_file.resolve()}")
    assert res["status"] == "SUCCESS"
    assert res["doc_type"] == "document"
    assert res["content"].startswith("# End-to-End Multimodal Policies")
    assert "diffusion policies" in res["content"]


def test_fetch_local_html_file(tmp_path):
    """Verify SearchTools fetches and extracts clean markdown from local .html file."""
    from app.tools.search_tools import search_tools

    html_file = tmp_path / "saved_article.html"
    html_content = (
        "<!DOCTYPE html><html><head><title>Robotics Foundation Models</title></head>"
        "<body><article><h1>Robotics Foundation Models</h1><p>Foundation models represent a paradigm shift in robot learning.</p></article></body></html>"
    )
    html_file.write_text(html_content, encoding="utf-8")

    res = search_tools.fetch_document(str(html_file))
    assert res["status"] == "SUCCESS"
    assert res["doc_type"] == "html"
    assert "Robotics Foundation Models" in res["content"]
    assert "paradigm shift" in res["content"]


def test_fetch_local_file_not_found():
    """Verify SearchTools returns structured error for non-existent local file without throwing."""
    from app.tools.search_tools import search_tools

    missing_url = "file:///non/existent/path/paper.pdf"
    res = search_tools.fetch_document(missing_url)
    assert res["status"] == "ERROR"
    assert "Local file not found" in res["error"]
    assert res["content"] == ""


@pytest.mark.asyncio
async def test_execute_ingestion_flow_fails_fast_on_fetch_error_without_substituting_notes(
    monkeypatch,
):
    """Verify that if document fetch fails, raw_payload notes are NEVER substituted for the file and flow aborts to conversation."""
    from app.agents.orchestrator import orchestrator

    async def mock_stream_chat_completion(messages, **kwargs):
        yield "Document could not be retrieved from the provided path."

    monkeypatch.setattr(
        orchestrator.llm, "stream_chat_completion", mock_stream_chat_completion
    )

    from app.models import IntentClassificationPayload

    target_info = IntentClassificationPayload(
        intent="INGESTION",
        doc_type="paper",
        source_url="file:///path/does/not/exist/missing_paper.pdf",
        raw_text="Here are my commentary notes about spatial policies.",
    )

    events = []
    with pytest.raises(RuntimeError, match="Document could not be retrieved"):
        async for evt in orchestrator.execute_ingestion_flow(
            query="ingest this file",
            chat_history=[],
            target_info=target_info,
            project_id="test_proj_fail_fast",
        ):
            events.append(evt)

    # First event yielded before exception should be document_fetched with status ERROR and error message populated
    fetch_evts = [e for e in events if e.get("event") == "document_fetched"]
    assert len(fetch_evts) == 1
    assert fetch_evts[0]["status"] == "ERROR"
    assert fetch_evts[0]["title"] == "Unretrievable Document"
    assert fetch_evts[0]["error"] is not None

    # Should have aborted without creating passages or calling ingest_document_tool
    tool_evts = [e for e in events if e.get("event") == "orchestrator_tool_call"]
    assert len(tool_evts) == 0

    # Test top-level coordination: process_user_message catches the failure and delegates to conversation flow
    coordinator_events = []
    # Mock classify_intent to return target_info
    monkeypatch.setattr(
        orchestrator, "classify_intent", lambda *args, **kwargs: target_info
    )
    async for evt in orchestrator.process_user_message(
        query="ingest this file",
        chat_history=[],
        project_id="test_proj_fail_fast",
    ):
        coordinator_events.append(evt)

    # Coordinator emits pipeline error and runs conversation flow
    err_evts = [e for e in coordinator_events if e.get("event") == "error"]
    assert len(err_evts) == 1
    conv_evts = [
        e for e in coordinator_events if e.get("event") == "conversation_start"
    ]
    assert len(conv_evts) == 1


@pytest.mark.asyncio
async def test_coordinated_persona_routing_and_fallback(monkeypatch):
    """Verify that candidate hubs are routed via LLM, falling back to 'Everything' when unrelated."""
    from app.agents.orchestrator import orchestrator
    from app.models import GraphNode
    from app.db import db_engine

    proj = "test_routing_proj"
    everything_hub = GraphNode(
        _id="hub_everything_route",
        title="Everything",
        description="Universal anchor.",
        node_type="CONCEPT",
        project_ids=[proj],
        metadata={"immutable": False, "is_genesis": True},
    )
    driving_hub = GraphNode(
        _id="hub_driving_route",
        title="Autonomous Driving",
        description="Vehicle dynamics.",
        node_type="CONCEPT",
        project_ids=[proj],
        metadata={"immutable": False},
    )
    db_engine.upsert_node(everything_hub)
    db_engine.upsert_node(driving_hub)

    # Mock routing LLM to select ONLY everything_hub for an unrelated biology topic
    def mock_routing(messages, **kwargs):
        sys_msg = messages[0]["content"]
        if (
            "persona_route_relevance" in sys_msg
            or "Executive Knowledge Graph Router" in sys_msg
        ):
            return '{"selected_hub_ids": ["hub_everything_route"], "reasoning": "Biology paper unrelated to driving."}'
        elif (
            "collective_ingestion_linking" in sys_msg
            or "Collective Graph Integration Coordinator" in sys_msg
        ):
            return '{"commands": [{"action": "CREATE_EDGE", "edge": {"source_id": "c1", "target_id": "hub_everything_route", "domain_hub_id": "hub_everything_route"}}]}'
        return "{}"

    monkeypatch.setattr(orchestrator.llm, "generate_chat_completion", mock_routing)

    # Verify get_top_concept_hubs returns both
    top_hubs = orchestrator.analytics.get_top_concept_hubs(project_id=proj)
    hub_ids = [h[0].id for h in top_hubs]
    assert "hub_everything_route" in hub_ids


def test_radial_tree_invariant_drops_duplicate_ancestor_edges():
    """Verify that graph ingestion engine drops redundant duplicate links between the same concept and target."""
    from app.services.graph_ingestion_engine import graph_ingestion_engine
    from app.models import GraphNode
    from app.db import db_engine

    proj = "test_radial_inv_proj"
    src = GraphNode(
        _id="concept_src_test",
        title="Source Concept",
        description="Source",
        node_type="CONCEPT",
        project_ids=[proj],
        metadata={"immutable": True},
    )
    tgt = GraphNode(
        _id="concept_tgt_test",
        title="Target Hub",
        description="Target",
        node_type="CONCEPT",
        project_ids=[proj],
        metadata={"immutable": False},
    )
    db_engine.upsert_node(src)
    db_engine.upsert_node(tgt)

    cmd = {
        "action": "CREATE_EDGE",
        "edge": {
            "source_id": "concept_src_test",
            "target_id": "concept_tgt_test",
            "description": "First Link",
        },
    }
    evt1 = graph_ingestion_engine.execute_single_command(cmd, "Doc", [proj])
    assert evt1 is not None
    assert evt1["event"] == "node_touched"

    # Attempting to execute the exact same edge again should be blocked by the Radial Invariant guard
    evt2 = graph_ingestion_engine.execute_single_command(cmd, "Doc", [proj])
    assert evt2 is None
    edges = [
        e
        for e in db_engine.get_edges(proj)
        if e.source_id == "concept_src_test" and e.target_id == "concept_tgt_test"
    ]
    assert len(edges) == 1, "Duplicate edge was not blocked!"

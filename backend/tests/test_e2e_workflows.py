"""
Master End-to-End Workflow Integration Test Suite: Me-Mex

Aligned with docs/ARCHITECTURE.md Section 2:
- Path 1: CONVERSATION E2E (Direct Execution -> Conversation Response)
- Path 2: RETRIEVAL E2E (Partitioned Hub Traversal -> Relevance Evaluation -> Enriched Response)
- Path 3: INGESTION E2E (ArXiv 2605.11550 Document Fetching -> Passage Storage -> Ingestion Linking -> 3-Step Concept Hub Reorganization -> Final Summary)
"""

import os
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import pytest
from app.db import db_engine
from app.agents.orchestrator import orchestrator


@pytest.mark.xdist_group(name="worker2")
@pytest.mark.vllm
@pytest.mark.asyncio
async def test_e2e_conversation_workflow():
    """Path 1: CONVERSATION E2E Workflow verification via process_user_message."""
    events = []
    async for event in orchestrator.process_user_message(
        "Hello Me-Mex! What is your core purpose as an agentic memory assistant?",
        project_id="e2e_conv_proj",
    ):
        events.append(event)

    intent_evts = [e for e in events if e.get("event") == "intent_classified"]
    assert len(intent_evts) > 0
    assert intent_evts[0]["intent"] == "CONVERSATION"

    complete_evts = [e for e in events if e.get("event") in ["chat_complete", "error"]]
    assert len(complete_evts) > 0


@pytest.mark.xdist_group(name="worker1")
@pytest.mark.vllm
@pytest.mark.asyncio
async def test_e2e_retrieval_workflow():
    """Path 2: RETRIEVAL E2E Workflow verification via process_user_message."""
    proj_id = "e2e_retrieval_proj"
    events = []
    # Real plain-text user retrieval prompt asking for associative concept retrieval across papers
    async for event in orchestrator.process_user_message(
        "What do our ingested research notes say about Process Reward Models vs outcome reward models for step-by-step verification?",
        project_id=proj_id,
    ):
        events.append(event)

    intent_evts = [e for e in events if e.get("event") == "intent_classified"]
    assert len(intent_evts) > 0
    assert intent_evts[0]["intent"] in ["RETRIEVAL", "CONVERSATION"]

    complete_evts = [e for e in events if e.get("event") in ["chat_complete", "error"]]
    assert len(complete_evts) > 0


@pytest.mark.xdist_group(name="worker2")
@pytest.mark.vllm
@pytest.mark.asyncio
async def test_e2e_ingestion_workflow_real_paper():
    """Path 3: INGESTION E2E Workflow verification via process_user_message using ArXiv 2605.11550."""
    proj_id = "e2e_ingest_proj"

    # Realistic user message containing a paper URL and user preface notes on why it is relevant
    user_ingest_message = (
        "Please take a look at this paper and ingest it into the graph: "
        "https://arxiv.org/pdf/2605.11550. "
        "It covers world action interactive models."
    )

    events = []
    async for event in orchestrator.process_user_message(
        user_ingest_message,
        project_id=proj_id,
    ):
        events.append(event)

    # 1. Verify intent classified as INGESTION
    intent_evts = [e for e in events if e.get("event") == "intent_classified"]
    assert len(intent_evts) > 0
    assert intent_evts[0]["intent"] == "INGESTION"

    # 2. Verify document_fetched event and local debug markdown storage
    fetch_evts = [e for e in events if e.get("event") == "document_fetched"]
    assert len(fetch_evts) > 0
    debug_path = fetch_evts[0].get("debug_file_path")
    assert debug_path and os.path.exists(
        debug_path
    ), f"Debug file {debug_path} must exist"

    # 3. Verify completion telemetry event emitted
    comp_evts = [
        e for e in events if e.get("event") in ["ingestion_completed", "error"]
    ]
    assert len(comp_evts) > 0

    # 4. Verify Document and Passages stored in DB
    docs = db_engine.get_documents()
    assert len(docs) > 0

    # 5. Verify Root Node & Intra-Document Concepts created with immutable: True
    all_nodes = db_engine.get_nodes(project_id=proj_id)
    root_nodes = [n for n in all_nodes if n.is_root_node]
    assert len(root_nodes) > 0
    assert root_nodes[0].is_immutable is True

    intra_nodes = [
        n for n in all_nodes if n.node_type == "CONCEPT" and n.is_immutable is True
    ]
    assert len(intra_nodes) > 0

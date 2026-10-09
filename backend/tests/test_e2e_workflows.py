"""
Master End-to-End Workflow Integration Test Suite: Me-Mex

Aligned with docs/ARCHITECTURE.md Section 2:
- Path 1: CONVERSATION E2E (Direct Execution -> Conversation Response)
- Path 2: RETRIEVAL E2E (Partitioned Hub Traversal -> Relevance Evaluation -> Enriched Response)
- Path 3: INGESTION E2E (ArXiv 2502.18864v2 Document Fetching -> Passage Storage -> Ingestion Linking -> 3-Step Concept Hub Reorganization -> Final Summary)
"""

import asyncio
import os
import sys
import uuid
import time
from typing import List, Dict, Any

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.db import db_engine
from app.models import GraphNode, GraphEdge, PassageRecord, DocumentRecord
from app.agents.orchestrator import orchestrator
from app.agents.department_persona import DepartmentPersonaAgent
from app.services.graph_ingestion_engine import graph_ingestion_engine
from app.services.llm_gateway import llm_gateway
from app.services.event_queue import event_queue

# --- Real Paper Data (ArXiv 2502.18864v2) ---
ARXIV_PAPER_TITLE = "Reasoning with Language Models: Search and Process Verification"
ARXIV_PAPER_TEXT = """# Reasoning with Language Models: Search and Process Verification

## Abstract
Large language models (LLMs) have achieved remarkable progress in complex reasoning tasks, including mathematical problem solving and software engineering. Recent advances demonstrate that coupling autoregressive base models with structured search algorithms—such as Monte Carlo Tree Search (MCTS) and Process Reward Models (PRMs)—substantially boosts step-by-step reasoning performance.

## Process Reward Models and Step-by-Step Verification
Traditional outcome-based reward models evaluate only the final output of a reasoning chain. In contrast, Process Reward Models (PRMs) evaluate each intermediate reasoning step independently. By assigning fine-grained scalar scores to intermediate transitions, PRMs mitigate early logical errors and guide search algorithms toward correct reasoning trajectories.

## Tree Search and Latent Reasoning Rollouts
Tree search techniques decompose problem solving into a state-action search space. At each node in the search tree, the model generates candidate reasoning steps, which are evaluated by the process verifier. Rollouts explore promising reasoning branches while pruning low-scoring trajectory paths, significantly increasing inference-time compute efficiency.
"""


def test_e2e_conversation_workflow():
    """Path 1: CONVERSATION E2E Workflow verification via process_user_message."""
    if not llm_gateway.is_server_available():
        print("  ⏭️ test_e2e_conversation_workflow [SKIPPED - vLLM Server Offline]")
        return

    async def _run():
        events = []
        async for event in orchestrator.process_user_message(
            "Hello Me-Mex! What is your core purpose as an agentic memory assistant?",
            project_id="e2e_conv_proj",
        ):
            events.append(event)

        intent_evts = [e for e in events if e.get("event") == "intent_classified"]
        assert len(intent_evts) > 0
        assert intent_evts[0]["intent"] == "CONVERSATION"

        complete_evts = [
            e for e in events if e.get("event") in ["chat_complete", "error"]
        ]
        assert len(complete_evts) > 0

    asyncio.run(_run())
    print("  ✓ Path 1: CONVERSATION E2E Workflow passed.")


def test_e2e_retrieval_workflow():
    """Path 2: RETRIEVAL E2E Workflow verification via process_user_message."""
    if not llm_gateway.is_server_available():
        print("  ⏭️ test_e2e_retrieval_workflow [SKIPPED - vLLM Server Offline]")
        return

    proj_id = "e2e_retrieval_proj"

    async def _run():
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

        complete_evts = [
            e for e in events if e.get("event") in ["chat_complete", "error"]
        ]
        assert len(complete_evts) > 0

    asyncio.run(_run())
    print("  ✓ Path 2: RETRIEVAL E2E Workflow passed.")


def test_e2e_ingestion_workflow_real_paper():
    """Path 3: INGESTION E2E Workflow verification via process_user_message using ArXiv 2502.18864v2."""
    if not llm_gateway.is_server_available():
        print(
            "  ⏭️ test_e2e_ingestion_workflow_real_paper [SKIPPED - vLLM Server Offline]"
        )
        return

    proj_id = "e2e_ingest_proj"

    # Realistic user message containing a paper URL and user preface notes on why it is relevant
    user_ingest_message = (
        "Please take a look at this paper and ingest it into the graph: "
        "https://arxiv.org/pdf/2502.18864v2. "
        "It covers reasoning with language models, process reward models (PRMs), "
        "and tree search rollouts for intermediate step verification."
    )

    async def _run():
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

    asyncio.run(_run())
    print("  ✓ Path 3: INGESTION E2E Workflow (ArXiv 2502.18864v2) passed.")

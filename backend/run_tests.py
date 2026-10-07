"""
Master Backend Test Suite Runner: Me-Mex (Optimized 2-Worker Concurrent Runner)

Aligned with docs/ARCHITECTURE.md Section 7:
- Executes test suite across max 2 parallel worker processes (-n 2 compliant).
- Isolates MongoDB databases into 'test-me-mex-w1' and 'test-me-mex-w2'.
- Worker 1 executes Fast Unit Tests (DB, Analytics, Intent, Immutability, Routes) + Path 1 & Path 2 Workflows.
- Worker 2 executes Path 3 Real Paper Ingestion Workflow (ArXiv 2502.18864v2) concurrently.
- Completes entire backend test suite in < 60 seconds.
"""

import os
import sys
import time
import multiprocessing

backend_dir = os.path.abspath(os.path.dirname(__file__))
if "" in sys.path:
    sys.path.remove("")
if backend_dir in sys.path:
    sys.path.remove(backend_dir)
sys.path.insert(0, backend_dir)

os.environ["TESTING"] = "1"

from tests.conftest import reset_test_database, teardown_test_database
from tests.test_db import (
    test_project_workspace_crud,
    test_node_and_edge_project_scoping,
    test_chat_message_persistence_and_isolation,
)
from tests.test_graph_analytics import (
    test_rustworkx_graph_construction,
    test_hub_centrality_calculation,
    test_project_scoped_concept_hubs,
    test_pure_centrality_dynamic_hub_selection,
)
from tests.test_orchestrator import (
    test_classify_intent_conversation,
    test_classify_intent_retrieval,
    test_classify_intent_ingestion,
    test_classify_intent_with_chat_history,
    test_consolidate_extracted_concepts,
)
from tests.test_concept_reconciliation import (
    test_independent_ingestion_linking,
    test_node_immutability_enforcement,
    test_mutable_concept_node_splitting,
)
from tests.test_department_persona import (
    test_department_persona_shared_exploration,
    test_department_persona_root_node_traversal_blocking,
    test_department_persona_mutually_exclusive_partitioning,
)
from tests.test_conversation import (
    test_conversation_flow_continuity,
    test_external_event_understanding,
)
from tests.test_e2e_workflows import (
    test_e2e_conversation_workflow,
    test_e2e_retrieval_workflow,
    test_e2e_ingestion_workflow_real_paper,
)
from tests.test_api_routes import (
    test_root_endpoint,
    test_projects_endpoints,
    test_graph_endpoint,
    test_chat_endpoint_post,
    test_project_chat_history_endpoint,
)
from fastapi.testclient import TestClient
from main import app
from app.services.llm_gateway import llm_gateway


def _run_worker_1(result_queue):
    """Worker 1: Fast Unit Tests, Routing, and Paths 1 & 2."""
    os.environ["DB_NAME"] = "test-me-mex-w1"
    server_online = llm_gateway.is_server_available()
    force_llm = os.getenv("SKIP_LLM", "0") != "1"

    worker_1_tests = [
        ("DB: Project Workspace CRUD", test_project_workspace_crud, False),
        ("DB: Node/Edge Project Scoping", test_node_and_edge_project_scoping, False),
        (
            "DB: Chat Message Persistence & Isolation",
            test_chat_message_persistence_and_isolation,
            False,
        ),
        ("Analytics: PyDiGraph Construction", test_rustworkx_graph_construction, False),
        ("Analytics: Hub Centrality Ranking", test_hub_centrality_calculation, False),
        (
            "Analytics: Project-Scoped Concept Hubs",
            test_project_scoped_concept_hubs,
            False,
        ),
        (
            "Analytics: Dynamic Pure Centrality Hub Selection",
            test_pure_centrality_dynamic_hub_selection,
            False,
        ),
        (
            "Reconciliation: Independent Ingestion Linking",
            test_independent_ingestion_linking,
            False,
        ),
        (
            "Reconciliation: Node Immutability Enforcement",
            test_node_immutability_enforcement,
            False,
        ),
        (
            "Reconciliation: Mutable Concept Splitting",
            test_mutable_concept_node_splitting,
            False,
        ),
        (
            "Persona: Mutually Exclusive Sub-Graph Partitioning",
            test_department_persona_mutually_exclusive_partitioning,
            False,
        ),
        (
            "Orchestrator: Consolidate Extracted Concepts",
            test_consolidate_extracted_concepts,
            False,
        ),
        ("Orchestrator: Conversation Intent", test_classify_intent_conversation, True),
        ("Orchestrator: Retrieval Intent", test_classify_intent_retrieval, True),
        ("Orchestrator: Ingestion Intent", test_classify_intent_ingestion, True),
        (
            "Orchestrator: Chat History Intent",
            test_classify_intent_with_chat_history,
            True,
        ),
        (
            "Persona: Sub-Graph Exploration",
            test_department_persona_shared_exploration,
            True,
        ),
        (
            "Persona: Root Node Traversal Blocking",
            test_department_persona_root_node_traversal_blocking,
            True,
        ),
        ("E2E Workflow: Path 1 Conversation", test_e2e_conversation_workflow, True),
        ("E2E Workflow: Path 2 Retrieval", test_e2e_retrieval_workflow, True),
    ]

    passed = 0
    failed = 0
    errors = []

    try:
        for name, func, requires_llm in worker_1_tests:
            if requires_llm and not server_online and not force_llm:
                print(f"  ⏭️ [W1] {name} [SKIPPED - vLLM Offline]")
                continue

            reset_test_database()
            try:
                func()
                print(f"  ✓ [W1] {name} passed.")
                passed += 1
            except Exception as e:
                print(f"  ❌ [W1] {name} FAILED: {e}")
                failed += 1
                errors.append((name, str(e)))
            finally:
                teardown_test_database()

        # API Route tests with TestClient
        with TestClient(app) as client:
            api_funcs = [
                ("API: Root Endpoint", test_root_endpoint, False),
                ("API: Projects Endpoints", test_projects_endpoints, False),
                ("API: Graph Endpoint", test_graph_endpoint, False),
                ("API: Chat POST Endpoint", test_chat_endpoint_post, True),
                (
                    "API: Project Chat History Endpoint",
                    test_project_chat_history_endpoint,
                    True,
                ),
            ]
            for name, func, requires_llm in api_funcs:
                if requires_llm and not server_online and not force_llm:
                    print(f"  ⏭️ [W1] {name} [SKIPPED - vLLM Offline]")
                    continue

                reset_test_database()
                try:
                    func(client)
                    print(f"  ✓ [W1] {name} passed.")
                    passed += 1
                except Exception as e:
                    print(f"  ❌ [W1] {name} FAILED: {e}")
                    failed += 1
                    errors.append((name, str(e)))
                finally:
                    teardown_test_database()

    finally:
        teardown_test_database()

    result_queue.put(("W1", passed, failed, errors))


def _run_worker_2(result_queue):
    """Worker 2: Ingestion E2E Workflow with Real ArXiv Paper."""
    os.environ["DB_NAME"] = "test-me-mex-w2"
    server_online = llm_gateway.is_server_available()
    force_llm = os.getenv("SKIP_LLM", "0") != "1"

    worker_2_tests = [
        (
            "E2E Workflow: Path 3 Real Paper Ingestion (ArXiv 2502.18864v2)",
            test_e2e_ingestion_workflow_real_paper,
            True,
        ),
    ]

    passed = 0
    failed = 0
    errors = []

    try:
        for name, func, requires_llm in worker_2_tests:
            if requires_llm and not server_online and not force_llm:
                print(f"  ⏭️ [W2] {name} [SKIPPED - vLLM Offline]")
                continue

            reset_test_database()
            try:
                func()
                print(f"  ✓ [W2] {name} passed.")
                passed += 1
            except Exception as e:
                print(f"  ❌ [W2] {name} FAILED: {e}")
                failed += 1
                errors.append((name, str(e)))
            finally:
                teardown_test_database()
    finally:
        teardown_test_database()

    result_queue.put(("W2", passed, failed, errors))


def run_all_tests():
    t_start = time.time()
    print("=== Running Backend Test Suite (2-Worker Parallel Runner, n=2) ===")

    force_llm = os.getenv("SKIP_LLM", "0") != "1"
    server_online = llm_gateway.is_server_available()

    if not server_online and not force_llm:
        print(
            "⚠️ [vLLM Colab Server Offline] LLM-dependent tests will be SKIPPED cleanly."
        )
    elif not server_online and force_llm:
        print(
            "⚡ [LLM Required Mode] Forcing LLM tests to execute against vLLM server..."
        )
    else:
        print("⚡ [vLLM Server Online] Executing tests against live vLLM model.")

    result_queue = multiprocessing.Queue()
    p1 = multiprocessing.Process(target=_run_worker_1, args=(result_queue,))
    p2 = multiprocessing.Process(target=_run_worker_2, args=(result_queue,))

    p1.start()
    p2.start()

    p1.join()
    p2.join()

    total_passed = 0
    total_failed = 0
    all_errors = []

    while not result_queue.empty():
        w_name, passed, failed, errors = result_queue.get()
        total_passed += passed
        total_failed += failed
        all_errors.extend(errors)

    t_elapsed = time.time() - t_start
    print(f"\n========================================================")
    print(f"TEST RUN COMPLETED in {t_elapsed:.2f} seconds!")
    print(f"Passed: {total_passed} | Failed: {total_failed}")
    if all_errors:
        print(f"\nFailures encountered:")
        for name, err in all_errors:
            print(f"  - {name}: {err}")
        sys.exit(1)
    else:
        print("🎉 All test assertions passed successfully!")
        print(f"========================================================\n")


if __name__ == "__main__":
    multiprocessing.set_start_method("spawn", force=True)
    run_all_tests()

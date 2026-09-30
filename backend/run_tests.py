import asyncio
import os
import sys
import unittest

backend_dir = os.path.abspath(os.path.dirname(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

os.environ["TESTING"] = "1"
os.environ["DB_NAME"] = "test-me-mex"

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
    test_classify_intent_direct,
    test_classify_intent_retrieval,
    test_classify_intent_ingestion,
    test_classify_intent_with_chat_history,
    test_consolidate_extracted_concepts,
)
from tests.test_concept_reconciliation import (
    test_reconciliation_no_conflict,
    test_reconciliation_conflict_debate,
    test_create_and_delete_commands,
)
from tests.test_department_persona import (
    test_department_persona_project_scoping,
    test_department_persona_shared_exploration,
    test_department_persona_root_media_traversal_blocking,
)
from tests.test_direct_conversation import (
    test_direct_conversation_flow_continuity,
    test_external_event_understanding,
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


def run_all_tests():
    print("=== Running Backend Test Suite on 'test-me-mex' Database ===")

    server_online = llm_gateway.is_server_available()
    if not server_online:
        print(
            "⚠️ [vLLM Colab Server Offline] LLM-dependent tests will be SKIPPED cleanly."
        )

    unit_test_funcs = [
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
        ("Orchestrator: Direct Intent", test_classify_intent_direct, True),
        ("Orchestrator: Retrieval Intent", test_classify_intent_retrieval, True),
        ("Orchestrator: Ingestion Intent", test_classify_intent_ingestion, True),
        (
            "Orchestrator: Chat History Intent",
            test_classify_intent_with_chat_history,
            True,
        ),
        (
            "Orchestrator: Consolidate Extracted Concepts",
            test_consolidate_extracted_concepts,
            False,
        ),
        (
            "Reconciliation: Path 1 (No Conflict)",
            test_reconciliation_no_conflict,
            False,
        ),
        (
            "Reconciliation: Path 2 (Multi-Persona Debate)",
            test_reconciliation_conflict_debate,
            False,
        ),
        (
            "Reconciliation: Command Mutations (CREATE/DELETE)",
            test_create_and_delete_commands,
            False,
        ),
        (
            "Persona: Project-Scoped Traversal",
            test_department_persona_project_scoping,
            True,
        ),
        (
            "Persona: Shared Exploration & Debate",
            test_department_persona_shared_exploration,
            True,
        ),
        (
            "Persona: Root Media Traversal Blocking",
            test_department_persona_root_media_traversal_blocking,
            True,
        ),
        (
            "Direct Conversation: Flow Continuity",
            test_direct_conversation_flow_continuity,
            True,
        ),
        (
            "Direct Conversation: External Event Understanding",
            test_external_event_understanding,
            True,
        ),
    ]

    try:
        for name, func, requires_llm in unit_test_funcs:
            if requires_llm and not server_online:
                print(f"  ⏭️ {name} [SKIPPED - vLLM Server Offline]")
                continue

            reset_test_database()
            try:
                func()
                print(f"  ✓ {name} passed.")
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
                if requires_llm and not server_online:
                    print(f"  ⏭️ {name} [SKIPPED - vLLM Server Offline]")
                    continue

                reset_test_database()
                try:
                    func(client)
                    print(f"  ✓ {name} passed.")
                finally:
                    teardown_test_database()

        print("\n=== BACKEND TEST SUITE EXECUTION COMPLETED! ===")
    finally:
        teardown_test_database()


if __name__ == "__main__":
    run_all_tests()

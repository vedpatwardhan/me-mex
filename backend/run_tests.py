import asyncio
import os
import sys
import unittest

backend_dir = os.path.abspath(os.path.dirname(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

os.environ["DB_NAME"] = "test-me-mex"

from tests.conftest import reset_test_database
from tests.test_db import (
    test_project_workspace_crud,
    test_node_and_edge_project_scoping,
    test_chat_message_persistence_and_isolation,
)
from tests.test_graph_analytics import (
    test_rustworkx_graph_construction,
    test_hub_centrality_calculation,
    test_project_scoped_concept_hubs,
)
from tests.test_orchestrator import (
    test_classify_intent_direct,
    test_classify_intent_retrieval,
    test_classify_intent_ingestion,
    test_classify_intent_with_chat_history,
    test_extract_document_title,
)
from tests.test_department_persona import test_department_persona_project_scoping
from tests.test_api_routes import (
    test_root_endpoint,
    test_projects_endpoints,
    test_graph_endpoint,
    test_chat_endpoint_post,
    test_project_chat_history_endpoint,
)
from tests.test_sse_telemetry import test_sse_chat_stream
from fastapi.testclient import TestClient
from main import app


def run_all_tests():
    print("=== Running Backend Test Suite on 'test-me-mex' Database ===")

    test_funcs = [
        ("DB: Project Workspace CRUD", test_project_workspace_crud),
        ("DB: Node/Edge Project Scoping", test_node_and_edge_project_scoping),
        (
            "DB: Chat Message Persistence & Isolation",
            test_chat_message_persistence_and_isolation,
        ),
        ("Analytics: PyDiGraph Construction", test_rustworkx_graph_construction),
        ("Analytics: Hub Centrality Ranking", test_hub_centrality_calculation),
        ("Analytics: Project-Scoped Concept Hubs", test_project_scoped_concept_hubs),
        ("Orchestrator: Direct Intent", test_classify_intent_direct),
        ("Orchestrator: Retrieval Intent", test_classify_intent_retrieval),
        ("Orchestrator: Ingestion Intent", test_classify_intent_ingestion),
        ("Orchestrator: Chat History Intent", test_classify_intent_with_chat_history),
        ("Orchestrator: Extract Title", test_extract_document_title),
        ("Persona: Project-Scoped Traversal", test_department_persona_project_scoping),
    ]

    for name, func in test_funcs:
        reset_test_database()
        func()
        print(f"  ✓ {name} passed.")

    # API Route tests with TestClient
    with TestClient(app) as client:
        api_funcs = [
            ("API: Root Endpoint", test_root_endpoint),
            ("API: Projects Endpoints", test_projects_endpoints),
            ("API: Graph Endpoint", test_graph_endpoint),
            ("API: Chat POST Endpoint", test_chat_endpoint_post),
            ("API: Project Chat History Endpoint", test_project_chat_history_endpoint),
            ("API: SSE Chat Stream", test_sse_chat_stream),
        ]
        for name, func in api_funcs:
            reset_test_database()
            func(client)
            print(f"  ✓ {name} passed.")

    print("\n=== ALL TEST SUITE MODULES PASSED SUCCESSFULLY! ===")


if __name__ == "__main__":
    run_all_tests()

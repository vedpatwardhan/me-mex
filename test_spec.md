# Test Specification & Verification Strategy: Graph-Memex (`me-mex`)

> **Document Purpose**: This document defines the complete backend testing specification, test database isolation strategy (`test-me-mex`), modular test suite structure, execution rules, and automated verification procedures for **Graph-Memex (`me-mex`)**.

---

## 1. Overview & Verification Strategy

The backend testing framework validates Graph-Memex's core agentic intelligence, database operations, graph analytics, REST endpoints, and SSE telemetry streams without requiring frontend UI interaction.

### Key Testing Principles:
1. **Dedicated Test Database (`test-me-mex`)**:
   - All tests execute against a dedicated isolated database named `test-me-mex` (configured via `DB_NAME="test-me-mex"` environment override).
   - Production `me-mex` database records are completely untouched during test execution.
   - The test fixture in `conftest.py` automatically clears all collections/in-memory stores before each test run and seeds baseline entities.
2. **Zero Headless UI Dependency**:
   - Every system feature (Graph retrieval, tool ingestion, multi-persona exploration, project chat isolation) is verified headlessly via Python unit/integration tests and FastAPI `TestClient`.
3. **Clean LLM Test Skipping when Offline**:
   - Tests requiring live LLM completions (Orchestrator intent classification, title extraction, persona traversal, chat endpoints) inspect `llm_gateway.is_server_available()`.
   - When the vLLM Colab server is disconnected or offline, LLM-dependent tests are **SKIPPED cleanly** (`⏭️ [SKIPPED - vLLM Server Offline]`) rather than passing via synthetic fallback or failing with connection errors.
4. **Execution Limits**:
   - Whenever parallel testing tools are invoked, worker count must **never exceed 2** (`-n 2`).
   - Python virtual environment executable: `me-mex/.venv/bin/python3.14`.

---

## 2. Test Suite Topology (`me-mex/backend/tests/`)

```
me-mex/backend/
├── tests/
│   ├── conftest.py                   # Pytest & TestClient fixtures targeting 'test-me-mex' database
│   ├── test_db.py                    # Database CRUD, project scoping, and chat persistence
│   ├── test_graph_analytics.py      # rustworkx eigenvector centrality & project-scoped hub discovery
│   ├── test_orchestrator.py         # ExecutiveOrchestrator intent router, title generator, & error handling
│   ├── test_department_persona.py   # DepartmentPersonaAgent project-scoped sub-graph traversal
│   ├── test_api_routes.py           # FastAPI REST endpoints (/api/chat, /api/graph, /api/projects, /api/projects/{id}/chat)
│   └── test_sse_telemetry.py        # SSE stream generator verification for GET /api/sse/chat
└── run_tests.py                      # Standalone test suite runner (runs all modular tests)
```

---

## 3. Test Module Specifications

### A. Database Operations (`tests/test_db.py`)
- **`test_project_workspace_crud`**: Verifies creation, retrieval, and storage of `ProjectWorkspace` records.
- **`test_node_and_edge_project_scoping`**: Verifies that `get_nodes(project_id)` and `get_edges(project_id)` return nodes/edges scoped to the active workspace while preserving global superset access (`project_id="global"`).
- **`test_chat_message_persistence_and_isolation`**: Verifies that user inputs and agent responses persist to MongoDB/Memory under `project_id` and do not leak across project workspace boundaries.

### B. Graph Analytics & Centrality (`tests/test_graph_analytics.py`)
- **`test_rustworkx_graph_construction`**: Verifies `build_rustworkx_graph()` converts DB nodes and edges into `rustworkx.PyDiGraph`.
- **`test_hub_centrality_calculation`**: Verifies eigenvector and degree centrality score calculation.
- **`test_project_scoped_concept_hubs`**: Verifies `get_top_concept_hubs(project_id)` ranks concept hubs filtered strictly by the specified workspace.

### C. Executive Orchestrator (`tests/test_orchestrator.py`)
- **`test_classify_intent_direct`**: Verifies `DIRECT_CONVERSATION` intent routing for greetings and math queries.
- **`test_classify_intent_retrieval`**: Verifies `GRAPH_RETRIEVAL` intent routing for research prompts.
- **`test_classify_intent_ingestion`**: Verifies `DOCUMENT_INGESTION` intent routing for arXiv paper links and text pastes.
- **`test_classify_intent_with_chat_history`**: Verifies context-aware follow-up intent classification using `chat_history`.
- **`test_extract_document_title`**: Verifies LLM-driven concise title generation (3–7 words) for ingested raw documents.

### D. Department Specialist Personas (`tests/test_department_persona.py`)
- **`test_department_persona_project_scoping`**: Verifies `DepartmentPersonaAgent.explore_and_debate_retrieval()` inspects only edges matching the active `project_id`.

### E. REST API Routes (`tests/test_api_routes.py`)
- **`test_root_endpoint`**: Verifies `GET /` system status response.
- **`test_projects_endpoints`**: Verifies `GET /api/projects` and `POST /api/projects`.
- **`test_graph_endpoint`**: Verifies `GET /api/graph?project_id=...` node and edge payload filtering.
- **`test_chat_endpoint_post`**: Verifies unified `POST /api/chat` intent evaluation, persona traversal execution, reply generation, and chat persistence.
- **`test_project_chat_history_endpoint`**: Verifies `GET /api/projects/{project_id}/chat` returns isolated message history.

### F. Telemetry SSE Streaming (`tests/test_sse_telemetry.py`)
- **`test_sse_chat_stream`**: Connects FastAPI `TestClient` stream to `GET /api/sse/chat?query=...&project_id=...` and verifies sequential JSON telemetry events (`intent_classified`, `node_touched`, `chat_complete`).

---

## 4. Execution Commands

Execute the complete test suite using the virtual environment Python interpreter:

```bash
# Execute standalone modular test runner
me-mex/.venv/bin/python3.14 me-mex/backend/run_tests.py

# Execute via pytest (if pytest is installed in environment, max 2 workers)
me-mex/.venv/bin/python3.14 -m pytest me-mex/backend/tests -v -n 2
```

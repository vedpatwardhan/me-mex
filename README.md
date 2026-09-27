# Graph-Memex (`me-mex`)

> **Agentic Knowledge Graph & Multi-Modal High-Volume Intake Engine**

Graph-Memex (`me-mex`) is an agentic research assistant and personal long-term memory system designed to digest massive streams of multi-modal content—including academic research papers, YouTube transcripts, lecture audio, codebase repositories, and experimental logs—without manual file scrolling or cognitive overload.

---

## 🏗️ The Operational System Architecture

Graph-Memex operates on a continuous **Conversational Gateway (`POST /api/chat`)** loop unifying Direct Conversation, Persona Retrieval, and Agentic Tool Ingestion:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        1. Multi-Modal Ingestion & Staging                              │
└────────────────────────────────────────────────────────────────────────────────────────┘
 - Staged Sandbox: Uploaded documents/links do NOT immediately populate the active graph.
 - Out-of-Graph Passage Storage: Text chunks are stored as plain text records in `passages`
   collection, linked only via `passage_pointers` inside atomic `CONCEPT` nodes.
 - Plain text retrieval: Passages are opened only when clicked to validate concept extraction.

┌────────────────────────────────────────────────────────────────────────────────────────┐
│                       2. Memory Storage & Clean 3-Element Topology                      │
└────────────────────────────────────────────────────────────────────────────────────────┘
 - Zero Passage Clutter: Passages are NOT graph nodes. The active network contains only:
     1. ROOT_MEDIA Nodes : Papers, Reports, Blogs, Transcripts, Code Repos.
     2. CONCEPT Nodes    : Self-evolving atomic notes (`title`, `text_body`, `passage_pointers`).
     3. CONNECTION_EDGE  : Qualitative relation edges (`source_id`, `target_id`, `text_body`).
 - Historical Edge Decay: Superseded relations decay in weight from `1.0` down to `0.3`
   (`HISTORICAL_SUPERSEDED`), preserving history without cluttering path searches.

┌────────────────────────────────────────────────────────────────────────────────────────┐
│               3. Unified Concept Hub Persona Exploration & Merging Debate               │
└────────────────────────────────────────────────────────────────────────────────────────┘
 - Dynamic Concept Hub Discovery: High-centrality concept nodes detected in real time (<5ms)
   via `rustworkx` eigenvector/degree centrality.
 - Shared Sub-Graph Exploration: Both Retrieval and Ingestion start with shared concept hub
   exploration (`explore_and_debate_hub`), sub-graph traversal, and optional DuckDuckGo search.
 - Relevance Debate: Personas debate the relevance of their domain knowledge against the user prompt,
   full conversation history (`chat_history`), and system execution events.
 - Multi-Persona Merging Debate (Ingestion Specific): Evaluates candidate concepts against each
   persona's hub domain knowledge, supporting concept decomposition, node merging, and multi-hub edge creation.
 - Real-Time SSE Telemetry: Streams persona traversal events (`traversing_node_ids`) to animate the
   WebGL canvas (`react-force-graph-2d`).

┌────────────────────────────────────────────────────────────────────────────────────────┐
│                      4. Agentic Tool Ingestion & Multi-Hub Integration                 │
└────────────────────────────────────────────────────────────────────────────────────────┘
 - Tool-Based Ingestion: Executive Orchestrator calls `ingest_document_tool` when URLs/PDFs are pasted.
 - Passage Chunking: Stores raw text chunks in `passages` collection.
 - Multi-Pass In-Memory Pre-Merge: Consolidates extracted concepts across passages.
 - Multi-Hub Edge Attachment: Links extracted concepts to multiple persona hubs across the graph.
```

---

## 🛠️ Technology Stack & Engine Architecture

* **Database Engine:** **MongoDB** document database (`documents`, `passages`, `nodes`, `edges`, `macro_documents`, `staging_sandbox`, `projects`, `chat_messages`) with in-memory fallback for local execution.
* **LLM Gateway:** **Ministral 3-8B** running remotely via Colab vLLM server (`http://localhost:8000/v1`) with local rule-based fallback.
* **Graph Analytics Worker:** **`rustworkx`** PyDiGraph for eigenvector/degree Hub Centrality ranking + **`NetworkX`** Louvain community partitioning.
* **Agent Protocol & Tools:** **FastMCP** (Python MCP SDK) exposing typed tools (`search_duckduckgo_web`, `search_arxiv_papers`, `fetch_web_article`, `get_graph_nodes`, `get_passages_by_ids`, `get_macro_documents`, `calculate_hub_rankings`).
* **Search Integrations:** **`arxiv`** API client and **`trafilatura`** web page markdown extractor.
* **Telemetry Streaming:** **FastAPI + SSE Starlette** streaming real-time colored persona node traversal events to the WebGL canvas.
* **Frontend Visualization:** **React + WebGL** (`react-force-graph-2d`), featuring off-canvas Markdown drawers and visual node highlights.

---

## 🚀 Backend Implementation & Verification Status

The backend engine (`me-mex/backend`) is fully implemented and verified:

- ✅ **`app/db.py`**: MongoDB Database Engine with models for Documents, Passages, Graph Nodes, Connection Edges, Project Workspaces, Chat Messages, and Staging Records.
- ✅ **`app/services/llm_gateway.py`**: vLLM gateway client targeting Colab Ministral 3-8B with local rule-based fallback.
- ✅ **`app/services/graph_analytics.py`**: `rustworkx` Hub Centrality worker & `NetworkX` Louvain community partitioner with project-scoped graph filtering.
- ✅ **`app/tools/search_tools.py`**: ArXiv research paper search and Trafilatura web article text extractor.
- ✅ **`app/agents/department_persona.py`**: Specialist Personas for shared sub-graph exploration, relevance debate, and multi-persona concept merging.
- ✅ **`app/agents/orchestrator.py`**: Executive Orchestrator coordinating Direct Conversation, Ingestion, and Persona Retrieval flows with `chat_history` context-aware intent classification.
- ✅ **`app/api/sse.py`**: FastAPI SSE endpoint (`/api/sse/chat`) streaming live persona traversal telemetry.
- ✅ **`main.py`**: REST API endpoints for unified chat (`POST /api/chat`), project workspaces (`GET/POST /api/projects`), project chat history (`GET /api/projects/{id}/chat`), and graph querying (`GET /api/graph?project_id=...`).
- ✅ **`tests/` & `run_tests.py`**: Pytest test suite and runner passing all database, project scoping, analytics, retrieval stream, concept merging, and API checks.

---

## 🧪 Running Backend Unit & Integration Tests

Run the test suite using the project virtualenv:

```bash
# Run backend test suite (max 2 parallel workers per project rule)
me-mex/.venv/bin/python3.14 me-mex/backend/run_tests.py
```


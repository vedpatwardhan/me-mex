# Me-Mex

> **Agentic Knowledge Graph & External Memory System**

Me-Mex is an agentic external memory system designed to function as an external extension of your brain for organizing, linking, and retrieving textual knowledge—including academic research papers, technical blogs, and YouTube video transcripts—without manual note scrolling or cognitive overload.

---

## 📚 Master Documentation Index

All master technical specs, research syntheses, and product roadmaps are consolidated in the `docs/` directory:

- 🏗️ **[`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md)**: Unified technical spec, 3-element topology, Node Mutability Hierarchy, 3-step persona workflows, API endpoints, and WebGL specs.
- 🔬 **[`docs/RESEARCH_SYNTHESIS.md`](./docs/RESEARCH_SYNTHESIS.md)**: Literature surveys on GraphRAG, HippoRAG 2, Stanford STORM, Google Co-Scientist, multi-agent debate frameworks, and deep-dive paper notes.
- 🗺️ **[`docs/ROADMAP.md`](./docs/ROADMAP.md)**: Strategic 5-phase execution roadmap (Backend $\rightarrow$ Testing $\rightarrow$ Frontend $\rightarrow$ End-to-End Interactivity $\rightarrow$ Fine-Tuning & Cortex-OS).

---

## 🏗️ The Operational System Architecture

Graph-Memex operates on a continuous **Conversational Gateway (`POST /api/chat`)** loop unifying **Conversation** (direct response), **Retrieval** (2 pre-steps $\rightarrow$ final conversation), and **Ingestion** (2 pre-steps $\rightarrow$ final conversation):

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        1. Document Ingestion & Staging                                 │
└────────────────────────────────────────────────────────────────────────────────────────┘
 - Staged Sandbox: Uploaded documents/links do NOT immediately populate the active graph.
 - Out-of-Graph Passage Storage: Text chunks are stored as plain text records in `passages`
   collection, linked only via `passage_ids` inside atomic `CONCEPT` nodes.
 - Plain text retrieval: Passages are opened only when clicked to validate concept extraction.

┌────────────────────────────────────────────────────────────────────────────────────────┐
│                       2. Memory Storage & Topology                                     │
└────────────────────────────────────────────────────────────────────────────────────────┘
 - Universal Genesis Concept Node (`concept_genesis` / "Everything"):
     - Primordial universal mutable knowledge anchor seeded in every empty workspace.
     - Guarantees cold-start hub availability: on first ingestion, "Persona Specialist: Everything" acts as the initial hub. Subsequent concepts attach to it and subdivide via `SPLIT_CONCEPT` as degree grows.
 - Strict Hub Criteria:
     - Root nodes and Immutable Concept nodes are **100% excluded** from candidate hubs.
     - Full graph topology (including immutable evidence edges) contributes to centrality calculation, but candidate hubs are strictly mutable concept nodes (`k <= 5`, $s_i \ge 0.3 \times s_{\max}$).
 - Zero Passage Clutter: Passages are NOT graph nodes. The active network contains:
     1. ROOT Nodes (Immutable)            : Base node for a paper, blog, transcript, or X post, shortly summarizing everything in that document.
     2. CONCEPT Nodes                     : Self-evolving atomic concepts.
        - Intra-Document Concepts (Immutable) : Factual concepts extracted directly from document text.
        - Domain & Intermediate Nodes (Mutable): Persona-created domain hub & bridge concepts.
     3. QUALITATIVE RELATION EDGES        : Typed structural edges (`SUBSET_OF`, `SUPERSET_OF`, `RELEVANT_TO`, `BUILDS_UPON`, `SUPERSEDES`, `PARALLEL_TO`, `CONTRASTS_WITH`) with contextual edge descriptions.
 - Local Raw Markdown Archive: Extracted documents automatically archive their full raw markdown to `backend/temp_downloads/` with metadata headers for inspection.
 - Comprehensive Telemetry: Real-time lifecycle events emitted for document fetching, chunking, extraction progress, consolidation, root creation, intra-concept creation, hub calculation, and partitioning.
 - First-Class Timestamps: Nodes and edges carry explicit creation/update timestamps (`created_at`, `updated_at`), enabling persona agents to reason about temporal progression and historical context naturally. Optional frontend toggles visualize timeline progression using color-coded time windows.

┌────────────────────────────────────────────────────────────────────────────────────────┐
│             3. Mutually Exclusive Concept Hub Exploration & Relevance Evaluation       │
└────────────────────────────────────────────────────────────────────────────────────────┘
 - Unweighted Topological Hub Discovery: Foundational concept hubs are detected in real time (<5ms) via `rustworkx` unweighted eigenvector centrality and community partitioning. Each detected concept hub is assigned a dedicated Specialist Persona representing domain expertise for that concept cluster.
 - Mutually Exclusive Sub-Graph Partitioning: Rather than overlapping hub traversals, the overall graph network is partitioned into mutually exclusive sub-graph regions across concept hubs. Each Specialist Persona independently explores its strictly assigned sub-graph region (`explore_concept_hub`) up to `max_depth = 3`.
 - Relevance Evaluation & Independent Operation: Because all intra-document concept nodes are completely immutable, proposals from different personas operate on disjoint/immutable nodes without conflicts.
 - Real-Time SSE Telemetry: Streams live persona traversal events (`traversed_node_ids`) to animate the WebGL canvas (`react-force-graph-2d`).

┌────────────────────────────────────────────────────────────────────────────────────────┐
│                      4. Agentic Tool Ingestion & Multi-Hub Integration                 │
└────────────────────────────────────────────────────────────────────────────────────────┘
 - Tool-Based Fetching & Construction: Executive Orchestrator calls `ingest_document_tool` when URLs/PDFs are pasted, storing text chunks in `passages` and building intra-document concept nodes.
 - Sub-Graph Traversal & Relevance Evaluation: Performs partitioned sub-graph traversal and relevance evaluation across concept hubs to determine optimal attachment points.
 - Multi-Hub Edge Attachment & Node Reorganization: Persona ingestion uses two direct options (`CREATE_EDGE` to link an immutable periphery concept to a domain hub, or `EDIT_CONCEPT` to update a domain hub). Macro node reorganization (`SPLIT_CONCEPT` / `reorganize_concept_hub`) executes a separated 3-step non-destructive loop (Discovery -> Grounded Sub-Concept Formulation -> Complete Neighbor Edge Re-Wiring), preserving the original concept hub as an umbrella node.
```

---

## 🛠️ Technology Stack & Engine Architecture

* **Database Engine:** **MongoDB** document database (`documents`, `passages`, `nodes`, `edges`, `macro_documents`, `staging_sandbox`, `projects`, `chat_messages`) with in-memory fallback for local execution.
* **LLM Gateway:** **Ministral 3-8B** running remotely via Colab vLLM server (`http://localhost:8000/v1`) with local rule-based fallback.
* **Graph Analytics Worker:** **`rustworkx`** PyDiGraph for fast (<1ms) eigenvector/degree Hub Centrality ranking with dynamic node-type filtering and relative score thresholding.
* **Agent Protocol & Tools:** **FastMCP** (Python MCP SDK) exposing typed tools (`search_duckduckgo_web`, `search_arxiv_papers`, `fetch_web_article`, `get_graph_nodes`, `get_passages_by_ids`, `get_macro_documents`, `calculate_hub_rankings`).
* **Search Integrations:** **`arxiv`** API client and **`trafilatura`** web page markdown extractor.
* **Telemetry & Response Streaming:** **FastAPI + SSE Starlette** streaming real-time token chunks and persona node traversal events to the client.
* **Speech-to-Text (STT) Dictation:** **Whisper-Base.en** (`@xenova/transformers`) running 100% locally in the browser via WebAssembly/WebGPU. Users dictate voice notes directly into the chat input box to review and edit before sending.
* **Frontend Visualization:** **React + WebGL** (`react-force-graph-2d`), featuring off-canvas Markdown drawers and visual node highlights.

---

## 🚀 Backend Implementation

- **`app/db.py`**: MongoDB Database Engine with models for Documents, Passages, Graph Nodes, Connection Edges, Project Workspaces, Chat Messages, and Staging Records.
- **`app/services/llm_gateway.py`**: vLLM gateway client targeting Colab Ministral 3-8B with local rule-based fallback.
- **`app/services/graph_analytics.py`**: `rustworkx` Hub Centrality worker with pure centrality dynamic thresholding and project-scoped graph filtering.
- **`app/tools/search_tools.py`**: ArXiv research paper search and Trafilatura web article text extractor.
- **`app/agents/department_persona.py`**: Specialist Personas for shared sub-graph exploration (`explore_concept_hub`), retrieval synthesis (`explore_and_retrieve`), and structured graph ingestion (`persona_ingestion`).
- **`app/agents/orchestrator.py`**: Executive Orchestrator coordinating Direct Conversation, Ingestion, and Persona Retrieval flows with `chat_history` context-aware intent classification.
- **`app/api/sse.py`**: FastAPI SSE endpoint (`/api/sse/chat`) streaming live persona traversal telemetry.
- **`main.py`**: REST API endpoints for unified chat (`POST /api/chat`), project workspaces (`GET/POST /api/projects`), project chat history (`GET /api/projects/{id}/chat`), and graph querying (`GET /api/graph?project_id=...`).
- **`tests/` & `run_tests.py`**: Pytest test suite and runner passing all database, project scoping, analytics, retrieval stream, concept merging, and API checks.

---

## 🧪 Running Backend Unit & Integration Tests

Run the test suite using the project virtualenv:

```bash
# Run backend test suite (max 2 parallel workers per project rule)
me-mex/.venv/bin/python3.14 me-mex/backend/run_tests.py
```

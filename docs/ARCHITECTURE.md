# Master Architecture & Technical Specification: Me-Mex

> **Document Purpose**: This document serves as the single master technical specification for **Me-Mex**, unifying system architecture, clean 3-element graph topology, Node Mutability Hierarchy, 3-step persona workflows, WebGL UI/UX specifications, REST/SSE API endpoints, FastMCP tools, and backend test specifications.

---

## 1. System Motivation & Macro Scope

Me-Mex is an **Agentic External Memory System** designed to function as an external extension of your brain for organizing, synthesizing, and retrieving textual knowledge—including academic research papers, technical blogs, and YouTube video transcripts—without manual note scrolling or cognitive overload.

### Core Problems Addressed
1. **Manual Overhead & Linear Scrolling**: Reviewing massive paper additions daily via linear text file scrolling is inefficient.
2. **Context Fragmentation**: Manually linking new papers to past literature or updating concept clusters requires high cognitive load.
3. **Implicit Relationships**: Complex cross-paper dynamics (supersedes, contrasts, co-occurs) are implicit rather than visually navigable.

---

## 2. Core Architecture & System Lifecycle

Me-Mex operates on a continuous **Conversational Gateway (`POST /api/chat`)** loop: **Input Intent Classification $\rightarrow$ Dynamic Concept Hub Traversal & Web Search $\rightarrow$ Orchestrator Tool Ingestion**.

```
       ┌──────────────────────────────────────────────────────────┐
       │         [User Message / Input pasted into Chat]           │
       └────────────────────────────┬─────────────────────────────┘
                                    │
                                    ▼
       [PHASE 0: UNIFIED CONVERSATIONAL GATEWAY (POST /api/chat)]
       - Executive Orchestrator analyzes query & chat history
       - Routes execution to ONE of three internal paths:
           1. DIRECT_CONVERSATION (Greetings, math, direct Q&A)
           2. GRAPH_RETRIEVAL     (Dynamic concept hubs, WebGL glowing)
           3. DOCUMENT_INGESTION  (Agent tool call: ingest_document_tool)
                                    │
           ┌────────────────────────┼────────────────────────┐
           │                        │                        │
           ▼                        ▼                        ▼
 [PATH 1: DIRECT CONVERSATION] [PATH 2: GRAPH RETRIEVAL]  [PATH 3: TOOL INGESTION]
 - Direct LLM stream           - Discover concept hubs   - Orchestrator calls
 - Zero persona overhead         via rustworkx           `ingest_document_tool`
 - Fast Q&A answer             - Persona traversal per   - Scrapes URL/PDF/Voice
                                 hub + DuckDuckGo search - Out-of-graph passages
                               - Stream glowing node IDs - Integrates concept node
```

### Operational Phases

1. **Phase 0: Conversational Gateway (`POST /api/chat` & `GET /api/sse/chat`)**
   - User inputs text, URLs, paper abstracts, or questions in a selected **Project Workspace** (`project_id`).
   - Executive Orchestrator evaluates prompt and `chat_history` context to route into `DIRECT_CONVERSATION`, `GRAPH_RETRIEVAL`, or `DOCUMENT_INGESTION`.
   - **Fast Non-Reasoning Intent Decoding**: `classify_intent` uses `enable_reasoning=False` and `max_tokens=128` to minimize latency.

2. **Phase 1: Dynamic Concept Hub Personas & Web Search**
   - Concept hubs discovered in real time (<5ms) using `rustworkx` eigenvector/degree centrality scoped to `project_id`.
   - Specialist Personas traverse multi-hop neighborhoods (`max_depth=3`), executing DuckDuckGo search if context is missing.
   - Real-time SSE telemetry streams active glowing node IDs (`traversed_node_ids`) to the visual canvas.

3. **Phase 2: Ingestion & Independent Concept Reorganization**
   - Ingestion executes `ingest_document_tool` autonomously, extracting plain-text `PassageRecord`s and immutable intra-document concept nodes.
   - Personas operate independently over mutually exclusive sub-graph partitions without consensus overhead or bilateral debates.

---

## 3. Clean 3-Element Topology & Universal Storage Schema

### Graph Topology & Node/Edge Classification

Passage text chunks are **NOT** graph nodes in the database network or UI visualizer. Including passages as nodes introduces visual "hairballs".

The active graph network consists of **Root Nodes**, **Concept Nodes (Immutable vs. Mutable)**, and **Typed Relation Edges**:

```mermaid
graph TD
    subgraph Active Graph Network Topology (No Passages)
        Paper[Root Node: Paper / Blog (Immutable)] -->|RELEVANT_TO| ConceptH[Domain Hub Node: World Models (Mutable)]
        ConceptH -->|BUILDS_UPON| ConceptPixel[Intra-Document Concept: Pixel World Models (Immutable)]
        ConceptH -->|BUILDS_UPON| ConceptLatent[Intra-Document Concept: Latent World Models (Immutable)]
        ConceptLatent <==>|SUPERSEDES| DownstreamTask[Intermediate Domain Node: MPC Planning (Mutable)]
        ConceptPixel -.->|HISTORICAL_SUPERSEDED| DownstreamTask
    end

    subgraph Out-of-Graph Database Storage
        Passage1[Plain Text Passage Chunk #101]
        Passage2[Plain Text Passage Chunk #102]
    end

    ConceptLatent -.->|ID Pointers in Metadata| Passage1
    ConceptLatent -.->|ID Pointers in Metadata| Passage2
```

### Node & Edge Schema Taxonomy

1. **`ROOT` Nodes (Immutable)**
   - Base node for an ingested paper, blog, transcript, or X post, shortly summarizing everything in that document. Cannot be modified or deleted.
2. **`CONCEPT` Nodes (Immutable vs. Mutable)**
   - **Intra-Document Concepts (`immutable: True`)**: Direct concepts originating from an ingested document. Preserves ground-truth evidence; personas can only link to them.
   - **Domain & Intermediate Nodes (`immutable: False`)**: Persona domain hubs and bridge nodes created during graph ingestion. Can be generalized (`EDIT_CONCEPT`) or restructured (`SPLIT_CONCEPT`).
3. **Qualitative Relation Edges (`GraphEdge`)**
   - Typed edges with qualitative descriptions contextualizing relationships:
     - **`SUBSET_OF`**: Concept $A$ is a specialized sub-type or narrower instance of Concept $B$.
     - **`SUPERSET_OF`**: Concept $A$ is an umbrella category or broader domain containing Concept $B$.
     - **`RELEVANT_TO`**: General semantic relevance link connecting an intra-document concept to a domain hub or intermediate concept.
     - **`BUILDS_UPON`**: Incremental theoretical or technical extension of an existing concept.
     - **`SUPERSEDES`**: New SOTA paradigm replacing or improving upon a historical concept.
     - **`PARALLEL_TO`**: Contemporary parallel approaches or competing paradigms.
     - **`CONTRASTS_WITH`**: Asymmetric contrast or explicit contradiction between concepts.

### First-Class Temporal Reasoning (No Artificial Weight Decay)

Rather than applying artificial floating-point weight decay (`1.0` down to `0.3`), all nodes and edges store explicit unix timestamps (`created_at`, `updated_at`).
- **Agent Reasoning**: Specialist Persona agents receive exact creation/update timestamps in their sub-graph context window, enabling natural LLM temporal reasoning (*"Concept A (2024) is superseded by Concept B (2026)"*) without arbitrary numerical penalties.
- **Frontend Timeline Visualizer**: The WebGL UI visualizer (`react-force-graph-2d`) provides an optional temporal timeline toggle, applying color-coded visual highlights across user-selected time windows.

The graph network enforces a strict **Hierarchy of Mutability**:

1. **Root Nodes (`ROOT`) — IMMUTABLE**
   - Base node for a paper, blog, transcript, or X post, shortly summarizing everything in that document. Cannot be modified or deleted.
2. **Intra-Document Concepts (`node_type="concept"`, Extracted) — IMMUTABLE**
   - Direct concepts extracted from the document. Preserves factual ground truth.
   - Personas **cannot** issue `EDIT_CONCEPT` or `DELETE_CONCEPT` targeting these nodes; they can **only link** to them.
3. **Domain Hub & Intermediate Concepts — MUTABLE**
   - Persona domain hub concepts and persona-created intermediate/bridge nodes.
   - Personas **can** create, edit/generalize (`EDIT_CONCEPT`), or split/restructure (`SPLIT_CONCEPT`) these nodes as new documents arrive.

```json
{
  "id": "concept_latent_world_models",
  "node_class": "CONCEPT",
  "node_type": "concept",
  "title": "Latent-Space World Models",
  "description": "Atomic self-evolving Markdown description & synthesis across papers...",
  "metadata": {
    "theme_id": "vla_research",
    "domain_tags": ["world_models", "latent_dynamics"],
    "status": "PRIMARY_ACTIVE",
    "immutable": false
  },
  "passage_ids": ["pass_chunk_101", "pass_chunk_102"]
}
```

---

## 4. Unified 3-Step Multi-Agent Persona Workflow

Both Retrieval and Ingestion operate on a unified multi-agent pattern structured around **Departments** (Thematic Concept Hubs):

1. **Mutually Exclusive Sub-Graph Exploration:**
   - **Unweighted Topological Hub Detection**: Identifies foundational keystone concepts in real time (<5ms) using `rustworkx` unweighted eigenvector centrality and community partitioning. Each detected concept hub is assigned a dedicated Specialist Persona representing domain expertise for that concept cluster.
   - **Mutually Exclusive Graph Partitioning**: The graph network is partitioned into mutually exclusive sub-graphs across concept hubs so persona explorations do not overlap.
   - **Iterative Multi-Hop Traversal**: Each Concept Hub Persona independently expands its strictly assigned sub-graph region up to `max_depth = 3`.
   - **Root Node Traversal Blocking**: Traversal visits Root Nodes for provenance context and summaries, but strictly **blocks Root Nodes from expanding further hops**.
2. **Relevance Evaluation & Retrieval-Step Reorganization:**
   - Each Specialist Persona evaluates the relevance of its accumulated domain nodes, search history, user prompt, and conversation history (`chat_history`) independently.
   - **Independent Concept Node Splitting**: At every retrieval step, each persona inspects its current sub-graph. If a mutable node has accumulated too many connections (over-clustering), the persona independently splits/reorganizes the concept (`SPLIT_CONCEPT`), referencing the underlying passage chunks (`passages`) corresponding to that concept for ground-truth reorganization.
3. **Independent Graph Ingestion & Linking:**
   - Consolidated concepts are ingested as **Immutable Intra-Document Concepts**.
   - Personas connect intra-document concepts to domain hubs independently using non-destructive actions:
     - **`CONNECT_DIRECT`**: Directly connect an immutable intra-document concept to a domain concept.
     - **`CREATE_INTERMEDIATE`**: Create a new domain bridge concept node and link through it.
     - **`EDIT_CONCEPT`**: Edit or generalize **existing domain or intermediate concepts** (mutations on immutable nodes are blocked).
     - **`SPLIT_CONCEPT`**: Restructure/split a domain node if its connection degree grows too large.
   - Because intra-document nodes are immutable and graph partitions are mutually exclusive, persona updates proceed completely independently.

---

## 5. WebGL UI/UX Specification & Visual Palette Mapping

### SPA Layout & Views
The SPA features a persistent canvas workspace and four view modes:
- **`🌐 Global Graph`**: Master superset graph visualization.
- **`📁 Project Workspace`**: Project-scoped graph view filtered by `project_id`.
- **`📄 Report Studio`**: Node-grounded markdown report editor.
- **`📥 Intake Stream`**: Drag-and-drop staging sandbox.

### Frontend Dynamic Palette Mapping
- Visual hex color palettes belong exclusively in the frontend UI (`GraphCanvas.tsx` / `useMemexStore.ts`).
- Backend streams clean `department_id` and `department_name` attributes over SSE.
- Frontend dynamically maps `department_id` string hashes to a high-contrast visual palette array (`['#38bdf8', '#fbbf24', '#c084fc', '#34d399', '#f87171', '#f43f5e', '#a855f7', '#06b6d4']`), rendering live node traversal glows.

---

## 6. API Endpoint Specification & FastMCP Tools

### REST API Routes
- `POST /api/chat`: Unified conversational gateway (Direct Q&A, Graph Retrieval, Document Ingestion).
- `GET /api/graph?project_id=...`: Retrieve clean 3-element graph topology.
- `GET /api/projects` & `POST /api/projects`: Project workspace CRUD.
- `GET /api/projects/{id}/chat`: Project-isolated conversation history.
- `GET /api/passages`: Fetch plain text passage records linked to atomic concepts.

### Telemetry Stream (`GET /api/sse/chat`)
Streams real-time JSON events: `intent_classified`, `node_touched`, `persona_debate_start`, `persona_debate_turn`, and `chat_complete`.

### FastMCP Tool Signatures
- `search_duckduckgo_web`, `search_arxiv_papers`, `fetch_web_article`, `get_graph_nodes`, `get_passages_by_ids`, `get_macro_documents`, `calculate_hub_rankings`.

---

## 7. Backend Test Specification & Verification

### Test Database Isolation (`test-me-mex`)
All tests execute against a dedicated isolated database named `test-me-mex` (`DB_NAME="test-me-mex"`). Production records are completely untouched.

### Execution Command
Execute tests via the project virtual environment:
```bash
me-mex/.venv/bin/python3.14 me-mex/backend/run_tests.py
```
*(When using parallel runners, worker count must never exceed 2: `-n 2`).*

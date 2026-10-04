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

Graph-Memex operates on a continuous **Conversational Gateway (`POST /api/chat`)** loop: **Input Intent Classification $\rightarrow$ Dynamic Concept Hub Traversal & Web Search $\rightarrow$ Orchestrator Tool Ingestion**.

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

3. **Phase 2: Ingestion & Bilateral Multi-Persona Debate**
   - Ingestion executes `ingest_document_tool` autonomously, extracting plain-text `PassageRecord`s and concept nodes.
   - Evaluates proposed commands across personas without upfront DB mutations. Conflicting commands trigger turn-by-turn bilateral dialogue loops (`run_bilateral_persona_debate`) until mutual consensus is reached.

---

## 3. Clean 3-Element Topology & Universal Storage Schema

### Zero Passage Clutter Principle
Passage text chunks are **NOT** graph nodes in the database network or UI visualizer. Including passages as nodes introduces visual "hairballs".

The active graph network consists **strictly of three node classes**:
1. **`ROOT_MEDIA` Nodes**: Papers, Reports, Blogs, Transcripts, Code Repos.
2. **`CONCEPT` Nodes**: Atomic self-evolving notes (`title`, `description`, `passage_ids`).
3. **`CONNECTION_EDGE`**: Qualitative relation edges (`source_id`, `target_id`, `description`, `weight`).

```mermaid
graph TD
    subgraph Active Graph Network Topology (No Passages)
        Paper[Root Media Node: Paper / Blog] -->|Emanates To| ConceptH[High-Level Concept Node: World Models]
        ConceptH -->|Child Concept| ConceptPixel[Pixel-Space World Models]
        ConceptH -->|Child Concept| ConceptLatent[Latent-Space World Models]
        ConceptLatent <==>|Active SOTA Link: weight=1.0| DownstreamTask[Action Planning via MPC]
        ConceptPixel -.->|Decayed Historical Link: weight=0.3| DownstreamTask
    end

    subgraph Out-of-Graph Database Storage
        Passage1[Plain Text Passage Chunk #101]
        Passage2[Plain Text Passage Chunk #102]
    end

    ConceptLatent -.->|ID Pointers in Metadata| Passage1
    ConceptLatent -.->|ID Pointers in Metadata| Passage2
```

### Node Mutability Hierarchy

The graph network enforces a strict **Hierarchy of Mutability** during ingestion and multi-persona debates:

1. **Root Media Nodes (`ROOT_MEDIA`) — IMMUTABLE**
   - Represents original source document or paper asset. Cannot be modified or deleted.
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

1. **Shared Multi-Hop Sub-Graph Exploration:**
   - `rustworkx` centrality identifies top project-scoped concept hubs.
   - **Iterative Multi-Hop Traversal**: Hub personas expand their frontier up to `max_depth = 3`.
   - **Root Media Traversal Blocking**: Traversal visits Root Media nodes for provenance context, but strictly **blocks Root Media nodes from expanding further hops**.
2. **Relevance Debate:**
   - Personas debate the relevance of their accumulated sub-graph context against the prompt and `chat_history`.
3. **Ingestion-Specific Concept Merging Debate:**
   - Consolidated concepts are presented as **Immutable Intra-Document Concepts**.
   - Personas connect intra-document concepts to domain hubs using non-destructive actions:
     - **`CONNECT_DIRECT`**: Directly connect an immutable intra-document concept to a domain concept.
     - **`CREATE_INTERMEDIATE`**: Create a new domain bridge concept node and link through it.
     - **`EDIT_CONCEPT`**: Edit or generalize **existing domain or intermediate concepts** (mutations on immutable nodes are blocked).
     - **`SPLIT_CONCEPT`**: Restructure/split a domain node if its connection degree grows too large.
   - Conflicting commands are clustered into `(Proposing Persona, Objecting Persona)` pairs that engage in interactive turn-by-turn dialogue loops (`run_bilateral_persona_debate`) until mutual consensus is reached.

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

# Project Specification: Graph-Memex (Agentic Knowledge Graph & Multi-Modal Intake Engine)

> **Document Purpose**: This document defines the master specification for **Graph-Memex (`me-mex`)**, unifying the project's core research use case with our agentic retrieval-first architecture, clean 3-element graph topology, universal node schema, dynamic intent classification, and human-in-the-loop multi-agent debate engine.

---

## 1. Overview & Motivation (Primary Use Case)

The primary operational use case of Graph-Memex is managing and synthesizing scientific literature, technical blogs, multi-modal transcripts, and engineering logs.

The research workflow relies on reading daily paper additions and maintaining multiple markdown files within the `docs/` directory:
- **`deeper_read_notes.md`**: Maintained list of papers with short (~2-line) summaries, plus a consolidated tool list at the bottom.
- **`overall_insights.md`**: Reverse index grouping papers into conceptual themes, architectural patterns, and paradigm clusters (e.g., *VLA Decoupling*, *World Models*, *Diffusion Policies*).
- **`select_papers.md`**: Detailed deep-dive notes for selected high-priority papers, including notes on technical blogs, articles, and surveys.
- **Deep Research Documents**: Standalone topic-focused research files providing comprehensive lessons on specific domains (e.g., `jepa_deep_dive.md`, `generative_notes.md`, `rl_landscape.md`, `data_engineering_stack.md`).

*(Note: `reports/` directory is explicitly excluded from this workflow).*

### Core Problems Addressed
1. **Manual Overhead & Scrolling**: Reviewing hundreds of papers daily via linear file scrolling is inefficient.
2. **Fragmented Context**: Manually linking new papers to past papers or updating reverse-index clusters in `overall_insights.md` requires high cognitive load and manual multi-file edits.
3. **Implicit Relationships**: Relationships between papers, technical blogs, tools, and overarching topic lessons are implicit rather than visually navigable.

---

## 2. Strategic Scope: High-Volume Multi-Theme Knowledge Engine

Graph-Memex serves as an **Ultra-Fast High-Volume Knowledge Intake Engine** partitioned into interconnected themes/workspaces:

```
+-----------------------------------------------------------------------------------+
|                        Multi-Theme Knowledge Intake Engine                        |
+-----------------------------------------------------------------------------------+
  |                                 |                                 |
  v                                 v                                 v
+-----------------------+ +-----------------------+ +-------------------------------+
| Theme A: Paper Notes  | | Theme B: Video/Audio  | | Theme C: Engineering & Code  |
|  - deeper_read_notes  | |  - YouTube Transcripts| |  - Data Engineering Stacks  |
|  - overall_insights   | |  - Lecture Transcripts| |  - Experimental Logs          |
|  - select_papers      | |  - Course Media       | |  - Codebase Repos           |
+-----------------------+ +-----------------------+ +-------------------------------+
```

### Macro Goals
- **Rapid Comprehension over Data Streams**: Digest massive multi-modal content (YouTube video transcripts, lecture audio, codebases, experimental logs, arXiv papers) without line-by-line manual scrolling.
- **Theme-Based Domain Partitioning**: Support isolated or interconnected **Themes/Workspaces** (e.g., *VLA Paper Research*, *YouTube Technical Transcripts*, *Experimental Logs*).
- **Cross-Theme Knowledge Bridges**: Discover and link nodes across themes (e.g., linking a paper node in Theme A to a video transcript explanation in Theme B).

---

## 3. Core Architecture & System Lifecycle

Graph-Memex operates on a **Single Conversational Gateway (`POST /api/chat`)** continuous loop: **Input Intent Classification $\rightarrow$ Dynamic Concept Hub Traversal & Web Search $\rightarrow$ Orchestrator Tool Ingestion**.

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

### Lifecycle Detailed Steps

1. **Phase 0: Single Conversational Gateway (`POST /api/chat` & `GET /api/sse/chat`)**
   - The user inputs text, a URL, a paper abstract, or a question within a selected **Project Workspace** (or `"global"` master superset).
   - The **Executive Orchestrator** evaluates the prompt in context of recent project `chat_history` and classifies intent into `DIRECT_CONVERSATION`, `GRAPH_RETRIEVAL`, or `DOCUMENT_INGESTION`.
   - **Non-Reasoning Fast Intent Decoding**: To minimize latency and eliminate unnecessary `[THINK]` token generation during routing, `classify_intent` and `_extract_document_title` query the LLM gateway with `enable_reasoning=False`, `max_tokens=128`, and strict `response_format={"type": "json_object"}`.
   - User messages and agent responses are automatically persisted to MongoDB / In-Memory store under `project_id` and isolated per workspace.

2. **Phase 1: Dynamic Project-Scoped Concept Hub Personas & Web Search**
   - Concept hubs are discovered in real time (<5ms) using `rustworkx` eigenvector/degree centrality filtered to the active `project_id` workspace.
   - A **Specialist Persona** is instantiated dynamically per top concept hub, receiving the user task, hub node text, and adjacent subgraph edges scoped to `project_id`.
   - If internal context is missing, the persona executes `duckduckgo_web_search` tool calls to retrieve live external evidence.
   - Streams active node highlights (`traversing_node_ids`) to animate the visual WebGL canvas in real time.

3. **Phase 2: Orchestrator Tool-Based Ingestion**
   - Ingestion is an agent tool call (`ingest_document_tool`) executed autonomously by the Orchestrator when URLs or documents are pasted.
   - Generates concise 3-7 word titles via LLM, creates plain-text out-of-graph `PassageRecord`s, extracts atomic `GraphNode` concepts, and links them via `GraphEdge` relations (`BUILDS_UPON`, `SUPERSEDES`, `PARALLEL_TO`) tagged with `project_ids: ["global", active_project_id]`.

---

## 4. Clean 3-Element Graph Topology & Universal Storage Schema

### Graph Topology Rule: Zero Passage Clutter
Passage text chunks are **NOT** graph nodes in the database network or UI visualizer. Including passage chunks as graph nodes introduces visual "hairballs" and structural clutter.

The active graph network consists **strictly of three node classes**:

```
+-----------------------------------------------------------------------------------+
|                            Clean 3-Element Graph Topology                         |
|                                                                                   |
|  1. ROOT_MEDIA Nodes : Papers, Reports, Blogs, Tweets, Code Repos.                |
|  2. CONCEPT Nodes    : Hierarchical shared ideas (High-Level -> Low-Level).       |
|  3. CONNECTION_EDGE  : Qualitative relation nodes (Agree, Disagree, Supersedes).  |
+-----------------------------------------------------------------------------------+
```

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

### Universal Node & Edge Schema

Every entity in the graph network adheres to a single universal node schema (`GraphNode`) and a dual-mode edge schema (`GraphEdge`). Passages exist purely as plain text database records referenced via ID pointers inside atomic concept notes:

```json
{
  "id": "concept_latent_world_models",
  "node_class": "CONCEPT",
  "node_type": "concept",
  "title": "Latent-Space World Models",
  "text_body": "Atomic self-evolving Markdown description & synthesis across papers...",
  "metadata": {
    "theme_id": "vla_research",
    "domain_tags": ["world_models", "latent_dynamics"],
    "status": "PRIMARY_ACTIVE"
  },
  "passage_pointers": ["pass_chunk_101", "pass_chunk_102"]
}
```

#### Dual-Mode Connection Edge Schema (`GraphEdge`)
Edges connect `ROOT_MEDIA` and `CONCEPT` nodes. The architecture explicitly supports **both directional and undirected (symmetric) edges** via `is_directional`:

```json
{
  "id": "edge_pixel_parallel_latent",
  "source_id": "concept_pixel_world_models",
  "target_id": "concept_latent_world_models",
  "is_directional": false,
  "text_body": "Parallel generative world model paradigms operating on raw pixels vs latent embeddings.",
  "weight": 1.0,
  "status": "PRIMARY_ACTIVE"
}
```

#### Complete Edge Taxonomy & Behavior Matrix

| Relation Predicate | Directional Mode (`is_directional`) | Graph Analytics Flow | Canvas Visual Rendering | Typical Use Case |
| :--- | :--- | :--- | :--- | :--- |
| **`BUILDS_UPON`** | `true` (Directional) | Directed $S \rightarrow T$ | Arrowhead from source to target | Incremental improvements or foundational theory. |
| **`SUPERSEDES`** | `true` (Directional) | Directed $S \rightarrow T$ | Bold arrow (with legacy 0.3 weight decay) | SOTA concept replacing an older paradigm. |
| **`EXTRACTED_FROM`** | `true` (Directional) | Directed $S \rightarrow T$ | Origin source arrow | Linking paper/blog node to an extracted concept. |
| **`CONTRASTS_WITH`** | `true` (Directional) | Directed $S \rightarrow T$ | Comparative arrow | Asymmetric comparison with specific nuance. |
| **`PARALLEL_TO`** | **`false` (Undirected)** | Reciprocal $S \leftrightarrow T$ | Clean solid line (no arrows) | Parallel contemporary paradigms (e.g., ACT vs Diffusion). |
| **`TRADE_OFF_WITH`** | **`false` (Undirected)** | Reciprocal $S \leftrightarrow T$ | Clean dashed/solid line | Symmetric trade-offs (e.g., Latency vs Expressivity). |
| **`CO_OCCURS_WITH`** | **`false` (Undirected)** | Reciprocal $S \leftrightarrow T$ | Subtle solid line | Frequently co-occurring domain topics. |

---

## 5. Persona-Driven Retrieval & Dynamic Color Palette Mapping

### Why Pure Vector Embeddings Fail at Graph Depth
Standard vector embeddings rely on surface-level cosine distance in static 1536-D space. They fail at arbitrary graph depth because they cannot perform relational multi-step deduction (*"Find papers that refute the reward formulation of LeWM"*), and semantic distance metrics degrade over multi-hop paths.

### Persona-Driven Retrieval Engine
1. **Dynamic Department Macro Documents (0 Hardcoding):**
   - Department Macro Documents are generated dynamically by graph analytics algorithms (`rustworkx` centrality + `NetworkX` Louvain partitioning).
   - Department titles are automatically derived from top concept hub titles (e.g., `Department of [Hub Concept Title]`).
2. **Specialist Persona Search Discourse:**
   - Active Specialist Personas traverse actual structural relationships (`BUILDS_UPON`, `CONTRASTS_WITH`, `SUPERSEDES`).
   - Personas debate relevance in the background and return structured perspectives.
3. **Frontend Dynamic Palette Mapping:**
   - Visual hex color palettes belong exclusively in the frontend UI (`GraphCanvas.tsx` / `useMemexStore.ts`).
   - The backend streams clean `department_id` and `department_name` attributes over SSE.
   - The frontend dynamically maps `department_id` string hashes to a high-contrast visual palette array (`['#38bdf8', '#fbbf24', '#c084fc', '#34d399', '#f87171', '#f43f5e', '#a855f7', '#06b6d4']`), rendering node highlights and glows seamlessly.

---

## 6. Dynamic Edge Weight Decay & Reference Case Study

To handle paradigm shifts without destructively deleting historical knowledge:

### Reference Case Study: Robotics World Models (Pixel vs. Latent Space)
```
                       [Concept: World Models]
                                  │
               ┌──────────────────┴──────────────────┐
               ▼                                     ▼
   [Pixel-Space World Models]           [Latent-Space World Models]
   (e.g., World Models 2018)            (e.g., LeWM, JEPA, Dreamer v3)
               │                                     │
               │ (Weight: 0.3 - Historical)          │ (Weight: 1.0 - Primary Active SOTA)
               └──────────────────┬──────────────────┘
                                  ▼
                    [Concept: Action Planning via MPC]
```

1. **Parallel Link Propagation:** When a downstream task concept (*Action Planning via MPC*) is linked to an older paradigm (`Pixel-Space World Models`), the engine infers/proposes a parallel connection to the newer paradigm (`Latent-Space World Models`).
2. **Dynamic Weight Decay (No Deletion):**
   - **New SOTA Link:** Instantiated with `weight: 1.0` and `status: "PRIMARY_ACTIVE"`.
   - **Legacy Link:** Retained with `weight: 0.3` and `status: "HISTORICAL_SUPERSEDED"`.
3. **UI Rendering & Retrieval Impact:**
   - Active SOTA links render as **bold solid high-contrast lines** in `react-force-graph`, while legacy links dim into **subtle dashed lines**.
   - PageRank prioritizes `weight: 1.0` paths during daily reviews while preserving full historical lineage.

---

## 7. Department Architecture & Incremental Macro Document Maintenance

Both Retrieval and Ingestion operate on a single unified multi-agent pattern structured around **Departments** (Thematic Concept Hubs).

```
                       [Compressed Macro Documents]
                       (Department Registry Overview)
                                      │
        ┌────────────────────────────┼────────────────────────────┐
        ▼                            ▼                            ▼
[Department 1 Persona]    [Department 2 Persona]    [Department 3 Persona]
(World Models Office)     (VLA Decoupling Office)   (Kinematics Office)
        │                            │                            │
        └────────────────────────────┼────────────────────────────┘
                                     ▼
                      [Executive Orchestrator Agent]
                                     │
             ┌───────────────────────┴───────────────────────┐
             ▼                                               ▼
     [RETRIEVAL MODE]                                [INGESTION MODE]
 1. Shared Concept Exploration                   1. Shared Concept Exploration
 2. Relevance Debate to Prompt                   2. Relevance Debate to Prompt
 3. Output Synthesis & Glows                     3. Multi-Persona Merging Debate
                                                    - Evaluates new concepts against local hub
                                                    - Decides merging, new nodes & edges
                                                    - Single concept can link to multiple hubs
```

### Unified Multi-Agent Persona Workflow

1. **Shared Sub-Graph Exploration:**
   - Both modes start by identifying top concept hubs via `rustworkx` centrality. Each hub persona retrieves its adjacent neighborhood (`GraphNode`s & `GraphEdge`s).
2. **Relevance Debate:**
   - Personas debate the relevance of their hub knowledge against the user prompt, full conversation history (`chat_history`), system events, and optional live web search evidence.
3. **Ingestion-Specific Concept Merging Debate:**
   - Ingestion executes an additional **Multi-Persona Merging Debate**. Each persona treats its hub neighborhood as its authoritative domain knowledge.
   - All extracted concepts from an ingested document are presented to every relevant persona.
   - Personas independently evaluate how the document's concepts map to their domain knowledge—merging into existing concepts, breaking down compound ideas, or connecting new nodes. If a concept is relevant to multiple personas, each persona creates its own connection edges (`GraphEdge`), attaching the concept to multiple hubs in the graph network.

---

## 8. Technology Stack & Technical Constraints

### A. Storage Architecture: MongoDB / In-Memory Fallback Engine
- **Constraint**: Do **NOT** use Neo4j.
- **Storage Model**: **MongoDB** (with automatic in-memory dictionary fallback for local development).
  - Storage partitioned across `nodes` (`ROOT_MEDIA`, `CONCEPT`), `edges` (`GraphEdge`), `documents`, `passages`, and `macros` collections.
  - Deep graph algorithms (Centrality rankings, Louvain hub partitioning) execute in Python memory via `rustworkx` or `scipy.sparse`.

### B. FastMCP Protocol & Bidirectional Markdown Sync
- **FastMCP Protocol**: Exposes atomic graph tools (`add_paper_node`, `connect_nodes`, `query_neighborhood`, `patch_macro_document`) via Python `fastmcp`.
- **Bidirectional Sync Engine**: Keeps local Markdown files (`deeper_read_notes.md`, `overall_insights.md`, `select_papers.md`) synchronized with backend storage.

### C. WebGL Frontend Visualizer
- Modern React WebGL visualizer (`react-force-graph-2d`) with custom canvas node styling, live traversal glow animations (`traversingNodeIds`), stationary camera controls on node selection, and side Markdown detail drawer.

---

## 9. API Endpoint Specification

This section details all backend REST API endpoints, real-time Server-Sent Events (SSE) telemetry streams, and FastMCP agent tools implemented in the `me-mex/backend` engine.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               Graph-Memex API Gateway                                  │
└────────────────────────────────────────────────────────────────────────────────────────┘
          │                                 │                                 │
          ▼                                 ▼                                 ▼
┌───────────────────┐             ┌───────────────────┐             ┌───────────────────┐
│  REST API Routes  │             │   SSE Streaming   │             │   FastMCP Server  │
│  (CRUD & Engine)  │             │  (Real-Time UI)   │             │  (Agent Tools)    │
└───────────────────┘             └───────────────────┘             └───────────────────┘
```

### A. Graph & Topology Endpoints

#### `GET /api/graph`
- **Purpose**: Fetch nodes and edges filtered by workspace/theme ID.
- **Parameters**: `project_id` (Query parameter, string, optional, default: `"global"`).
- **Behavior**: Returns the active clean 3-element graph topology (`ROOT_MEDIA`, `CONCEPT`, `CONNECTION_EDGE`). When `project_id="global"`, returns the master superset.

#### `GET /api/nodes/{node_id}`
- **Purpose**: Retrieve a single node record along with its incoming and outgoing connection edges and associated passage pointers.

#### `POST /api/nodes`
- **Purpose**: Create or upsert a new `GraphNode` in backend storage.

#### `POST /api/edges`
- **Purpose**: Create or update a `GraphEdge` record between two existing concept or media nodes.

---

### B. Out-of-Graph Passage & Document Storage Endpoints

#### `GET /api/passages`
- **Purpose**: Retrieve plain text passage records linked to atomic `CONCEPT` nodes via `passage_pointers`.

#### `POST /api/documents`
- **Purpose**: Register original source document metadata (arXiv papers, blogs, video transcripts) and save source file record.

---

### C. Staging & Intake Endpoints

#### `POST /api/intake`
- **Purpose**: Stage raw intake stream (URL, text snippet, PDF file path, or voice transcript) into the Staging Sandbox before graph integration.

---

### D. Real-Time Telemetry SSE Streams

#### `GET /api/sse/chat`
- **Purpose**: Unified real-time Server-Sent Events (SSE) chat stream handling intent classification (`DIRECT_CONVERSATION`, `GRAPH_RETRIEVAL`, `DOCUMENT_INGESTION`) and streaming real-time event updates.
- **Parameters**: `query` (Query parameter, string, e.g., `"Hello"` or `"Explain latent world models"`).

#### `GET /api/sse/retrieval`
- **Purpose**: Real-time SSE telemetry stream for User Flow 2 (Multi-Persona Graph Retrieval).
- **Stream Event Sequence**:
  1. `orchestrator_start`: Initiates Executive Orchestrator retrieval pass.
  2. `persona_traversal_start`: Emits Department Specialist Persona traversal initiation with clean `department_id` and `department_name`.
  3. `persona_traversal_active`: Emits active `traversing_node_ids` for live WebGL canvas glowing animation.
  4. `retrieval_complete`: Streams final executive synthesis and persona findings.

#### `GET /api/sse/ingestion`
- **Purpose**: Real-time SSE telemetry stream for User Flow 1 (Document Ingestion & Graph Evolution).
- **Stream Event Sequence**:
  1. `ingestion_staged`: Document & plain text passages stored in out-of-graph records.
  2. `persona_ingestion_debate`: Department personas evaluate candidate concepts against existing graph nodes.
  3. `human_in_the_loop_prompt`: Emits interactive clarification prompt for chat UI when trade-offs or edge superseding ambiguities arise.
  4. `ingestion_complete`: Commits evolved nodes with passage pointers and updates Department Macro Documents.

---

### E. Macro Documents & Graph Analytics Endpoints

#### `GET /api/macros`
- **Purpose**: Retrieve Department Macro Documents summarizing partitioned graph communities.

#### `POST /api/analytics/repartition`
- **Purpose**: Trigger `rustworkx` Hub Centrality ranking and `NetworkX` Louvain community partitioning to patch Department Macro Documents.

---

### F. FastMCP Agent Tools Protocol Server

The FastMCP server (`me-mex/backend/app/mcp/server.py`) exposes agentic tools over standard MCP JSON-RPC protocol:

| MCP Tool Name | Arguments | Functionality Description |
| :--- | :--- | :--- |
| `search_arxiv_papers` | `query: str, max_results: int` | Queries ArXiv API for relevant paper metadata and abstracts. |
| `fetch_web_article` | `url: str` | Uses Trafilatura to fetch and extract clean plain-text markdown from blogs/web pages. |
| `get_graph_nodes` | `theme_id: str` | Fetches all active atomic graph nodes for agent context windows. |
| `get_passages_by_ids` | `passage_ids: List[str]` | Retrieves plain text out-of-graph passage records for evidence auditing. |
| `get_macro_documents` | None | Retrieves Department Macro Documents for high-level domain routing. |
| `calculate_hub_rankings` | None | Runs `rustworkx` eigenvector/degree centrality algorithm to identify primary concept hubs. |

### G. External Web Search MCP Server (`duckduckgo-mcp-server`)

For real-time internet search and concept clarification, agents use the Python-based DuckDuckGo MCP server launched via `uvx`:

```json
{
  "mcpServers": {
    "duckduckgo": {
      "command": "uvx",
      "args": ["duckduckgo-mcp-server"]
    }
  }
}
```

| External MCP Tool | Arguments | Description |
| :--- | :--- | :--- |
| `duckduckgo_web_search` | `query: str, count: int` | Searches DuckDuckGo for live web results, snippets, and page URLs. |

---

## 10. Implementation Phasing

- **Phase 1**: Universal Graph Schema, FastMCP Server, & Bidirectional Markdown Sync Engine.
- **Phase 2**: React + WebGL Canvas (`react-force-graph`) with Dynamic Palette Assignment, Live Traversal Glow, & Markdown Side Drawer.
- **Phase 3**: Dynamic Executive Intent Classifier (`DIRECT_CONVERSATION`, `GRAPH_RETRIEVAL`, `DOCUMENT_INGESTION`) & Zero-Fallback Persona Retrieval.
- **Phase 4**: User-Triggered Ingestion Pipeline with Staged Conversational Sandbox, Human-in-the-Loop Multi-Agent Debate, & Incremental Delta Macro Patching.

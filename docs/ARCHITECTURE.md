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

Me-Mex operates on a continuous **Conversational Gateway (`POST /api/chat`)** loop. While **Conversation** streams a response straightaway, **Retrieval** and **Ingestion** execute preliminary processing steps before culminating in a final **Conversation** response:

```
       ┌──────────────────────────────────────────────────────────┐
       │         [User Message / Input pasted into Chat]           │
       └────────────────────────────┬─────────────────────────────┘
                                    │
                                    ▼
       [PHASE 0: UNIFIED CONVERSATIONAL GATEWAY (POST /api/chat)]
       - Executive Orchestrator analyzes query & chat history
       - Routes execution to ONE of three internal paths:
           1. CONVERSATION (Direct execution -> Conversation response)
           2. RETRIEVAL    (Step 1: Partitioned Hub Traversal -> Step 2: Relevance Evaluation -> Final Conversation)
           3. INGESTION    (Step 1: Fetch URL & Build Intra-Doc Graph -> Step 2: Hub Traversal, Relevance Eval & Reorg/Linking -> Final Conversation)
                                    │
           ┌────────────────────────┼────────────────────────┐
           │                        │                        │
           ▼                        ▼                        ▼
     [CONVERSATION]            [RETRIEVAL]              [INGESTION]
  (Direct Execution)      (Step 1: Hub Traversal    (Step 1: Fetch URL & Build
  - Immediate LLM         - Step 2: Domain Node       Intra-Document Graph
    response stream          Relevance Evaluation)  - Step 2: Hub Traversal,
                                                       Relevance Eval, Link
                                                       & Reorganize/Split)
           │                        │                        │
           └────────────────────────┴────────────────────────┘
                                    │
                                    ▼
                 [FINAL CONVERSATION RESPONSE STREAM]
                 - Synthesizes retrieved / ingested context
                 - Streams final answer to user in chat UI
```

### Operational Path Breakdown

1. **Path 1: `CONVERSATION` (Single-Step Direct Response)**
   - **Direct Execution**: Fast-path for greetings, quick questions, and direct synthesis without graph overhead. Streams the conversation response straightaway.
2. **Path 2: `RETRIEVAL` (Two Pre-Steps $\rightarrow$ Final Conversation Response)**
   - **Pre-Step 1 (Partitioned Sub-Graph Traversal)**: Discovers unweighted eigenvector hubs and assigns Specialist Personas to explore mutually exclusive sub-graph partitions.
   - **Pre-Step 2 (Relevance Evaluation)**: Personas evaluate domain relevance across their explored nodes, user prompt, and conversation history (`chat_history`).
   - **Final Conversation**: With enriched topological graph context assembled, the system triggers the final conversation step to generate and stream the response to the user.
3. **Path 3: `INGESTION` (Two Pre-Steps $\rightarrow$ Final Conversation Response)**
   - **Pre-Step 1 (Document Fetching & Intra-Document Graph Construction)**: Orchestrator calls `ingest_document_tool` to fetch and extract content dynamically:
     - **Universal Source Resolution**: Transparently ingests remote HTTP/HTTPS URLs (arXiv, blogs, HTML articles) and local filesystem references (`file:///...`, absolute paths `/Users/...`, `~/...`). Dispatches to format-specialized extractors:
       - **PDFs (`.pdf`, `%PDF`)**: Binary stream reading, ArXiv metadata detection, PDF layout text extraction.
       - **HTML (`.html`, `.htm`)**: Clean markdown extraction using Trafilatura with title metadata extraction.
       - **Markdown (`.md`, `.markdown`)**: Direct UTF-8 ingestion preserving existing heading hierarchies.
       - **Plain Text / Notes (`.txt`, `.log`, raw text)**: UTF-8 ingestion with automatic top-level header synthesis (`# {stem}`).
     - **Scale-Adaptive Document Chunking (1 to 30 Passages)**: Dynamically partitions the text into $N \in [1, 30]$ passages:
       - Tier 1 ($\le 1,500$ chars, X posts / quick notes): **1 chunk** (no artificial splitting).
       - Tier 2 ($1,500 < L \le 4,000$ chars, short memos): **2 chunks**.
       - Tier 3 ($4,000 < L \le 8,000$ chars, medium articles): **3 chunks**.
       - Tier 4 ($8,000 < L \le 14,000$ chars, multi-section overviews): **4 chunks**.
       - Tier 5 ($14,000 < L \le 25,000$ chars, short papers / reports): **5 chunks**.
       - Tier 6 ($L > 25,000$ chars up to $\ge 300\text{k}$ chars): scales from 5 to 30 chunks:
         $$N_{\text{target}} = \min\left(30, \max\left(5, 5 + \left\lfloor \frac{\text{len}(\text{text}) - 25000}{11000} \right\rfloor\right)\right)$$
     - **LLM Context Budget & Ceiling Guarantee**: Individual chunks are bounded at $\le 45,000$ characters (~13,000 tokens), preventing Ministral 3-8B's 16,384-token context window from overflowing while allowing 1,536 tokens for concept extraction.
     - **Density-Aware Concept Extraction & Scale-Aware Consolidation**:
       - Passages extract **1 to 3 atomic concepts** (1 for focused notes, 2–3 for dense passages; max 3).
       - Canonical consolidation scales naturally: preserves 1–5 canonical concepts for small inputs ($\le 6$ raw concepts) without forcing artificial expansion, and consolidates down to 6–10 canonical concepts for large inputs ($> 10$ raw concepts).
   - **Pre-Step 2 (Sub-Graph Traversal, Relevance Evaluation, Linking & Reorganization)**: Performs partitioned sub-graph traversal and relevance evaluation across concept hubs. Personas link newly ingested intra-document concepts to existing domain hubs, and independently reorganize/split over-clustered mutable concept nodes (`SPLIT_CONCEPT`) using underlying passage context.
   - **Final Conversation**: Once graph integration and reorganization complete, the system triggers the final conversation step to provide an executive summary and confirmation response to the user.

---

## 3. Clean 3-Element Topology & Universal Storage Schema

### Graph Topology & Node/Edge Classification

The active graph network operates on an eventual **Spherical Topology Model**:
- **Periphery (Outer Shell)**: `ROOT` nodes (immutable base documents/papers) and extracted factual **Intra-Document Concepts** (immutable evidence).
- **Core (Inner Hubs)**: Dynamic, mutable **Persona Domain Hubs & Intermediate Nodes** that cluster and evolve over time.
- **Typed Relation Edges**: Connect immutable periphery concepts inward to mutable domain hubs or link core hubs together.

```mermaid
graph TD
    subgraph Active Graph Network Topology (No Passages)
        Paper[Root Node: Paper / Blog (Immutable)] -->|RELEVANT_TO| ConceptPixel[Intra-Document Concept: Pixel World Models (Immutable)]
        Paper -->|RELEVANT_TO| ConceptLatent[Intra-Document Concept: Latent World Models (Immutable)]
        ConceptPixel -->|SUBSET_OF| ConceptH[Persona Domain Hub Node: World Models (Mutable)]
        ConceptLatent -->|SUBSET_OF| ConceptH
        ConceptH <==>|SUPERSEDES| DownstreamTask[Persona Intermediate Node: MPC Planning (Mutable)]
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

### First-Class Temporal Reasoning

All nodes and edges store explicit unix timestamps (`created_at`, `updated_at`).
- **Agent Reasoning**: Specialist Persona agents receive exact creation/update timestamps in their sub-graph context window, enabling natural LLM temporal reasoning (*"Concept A (2024) is superseded by Concept B (2026)"*).
- **Frontend Timeline Visualizer**: The WebGL UI visualizer (`react-force-graph-2d`) provides an optional temporal timeline toggle, applying color-coded visual highlights across user-selected time windows.

The graph network enforces a strict **Hierarchy of Mutability**:

1. **Universal Genesis Concept Node (`concept_genesis` / "Everything") — MUTABLE**
   - Primordial universal mutable knowledge anchor initialized automatically in every empty workspace.
   - Solves the hub cold-start paradox: provides the initial "Persona Specialist: Everything" anchor for the first document's intra-document concepts to attach to, later subdividing organically via `SPLIT_CONCEPT` as degree exceeds threshold.
2. **Root Nodes (`ROOT`) — IMMUTABLE**
   - Base node for a paper, blog, transcript, or X post, summarizing the document. Cannot be modified or deleted. Strictly excluded from being hubs.
3. **Intra-Document Concepts (`node_type="concept"`, Extracted) — IMMUTABLE**
   - Concept nodes directly originating from and connected to a Root Node during ingestion. Preserves factual ground truth.
   - Personas **cannot** modify, restructure, or delete these nodes; they can **only link** from them. Strictly excluded from being hubs.
4. **Persona Domain Hubs & Intermediate Concepts — MUTABLE**
   - Concept nodes created deeper in the graph by personas during ingestion for linking, synthesizing, or grouping concepts across documents.
   - Personas **can** create, edit/generalize (`EDIT_CONCEPT`), or restructure/split (`SPLIT_CONCEPT`) these nodes as new documents arrive.
   - Hub Centrality dynamically identifies top mutable hubs ($k \le 5$, relative score threshold $s_i \ge 0.3 \times s_{\max}$). All Root and Immutable Concept nodes are 100% excluded from candidate hubs.

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
   - **Unweighted Topological Hub Detection**: Identifies foundational keystone concepts in real time (<5ms) using `rustworkx` unweighted eigenvector centrality with relative thresholding ($s_i \ge 0.30 \times s_{\max}$). Each detected concept hub is assigned a dedicated Specialist Persona representing domain expertise for that concept cluster.
   - **Mutually Exclusive Voronoi Graph Partitioning**: The graph network is partitioned via multi-source topological shortest-path (Voronoi) distance anchored directly to the detected department hubs ($H = [h_1, \dots, h_m]$). Every node $v$ is assigned to its closest hub $h^*(v) = \arg\min d(v, h_i)$ (with ties resolved by hub centrality). Partitions are keyed directly by `hub_node.id`, guaranteeing $P_i \cap P_j = \emptyset$ and eliminating key-name mismatches.
   - **Iterative Multi-Hop Traversal**: Each Concept Hub Persona independently expands its strictly assigned sub-graph partition (`partition_node_ids`) up to `max_depth = 3`.
   - **Root Node Traversal Blocking**: Traversal visits Root Nodes for provenance context and summaries, but strictly **blocks Root Nodes from expanding further hops**.
2. **Relevance Evaluation:**
   - Each Specialist Persona evaluates the relevance of its accumulated domain nodes, search history, user prompt, and conversation history (`chat_history`) independently.
3. **Independent Graph Ingestion, Linking & 3-Step Concept Reorganization:**
   - Consolidated concepts are ingested as **Immutable Intra-Document Concepts** on the periphery of the spherical topology.
   - During persona ingestion, personas integrate intra-document concepts via **`CREATE_EDGE`** (connecting periphery concepts to core domain hubs) or **`EDIT_CONCEPT`** (updating mutable domain hubs).
   - **Priority Immutable-First Outward Movement Concept Hub Reorganization**:
     - **Step 1 (Candidate Screening & Discovery)**:
       - Computes dynamic degree threshold $\tau = \max(3, \lfloor \text{p75}(\text{degrees}) \rfloor)$ across the graph.
       - Discovers qualifying mutable hubs ($\text{deg}(H) \ge \tau$) and prompts the persona to produce structured candidate rationales.
     - **Step 2 (Neighborhood Analysis & Linear Outward Partitioning)**:
       - Direct neighbors $N(H)$ are classified into immutable leaves $N_{imm}$ and mutable concepts $N_{mut}$.
       - Resolves **immutable neighbors first across all candidate hubs**:
         1. **Immutable Leaves Outward Absorption (if $|N_{imm}| > 0$)**:
            - *Purely Immutable ($|N_{mut}| == 0$)*: Leaves move outward into $k_{new} \ll |N_{imm}|$ intermediate mutable sub-concepts. Reorganization terminates.
            - *Mixed ($|N_{mut}| > 0$, Phase 2a)*: Clusters raw evidence leaves into $k_{new}$ clean abstractions, passing existing mutable nodes as negative exclusion context to guarantee mutual exclusivity.
            - *Dynamic Degree Shrinkage Re-Evaluation*: Post-2a degree $\text{deg}'(H) = |N_{mut}| + k_{new}$ is recalculated. If $\text{deg}'(H) < \tau$, the hub has decongested and reorganization completes cleanly (Phase 2b skipped). If $\text{deg}'(H) \ge \tau$, the newly formulated sub-concepts are added to $N_{mut}$ and fall through into step 2.
         2. **Pure Mutable Outward Partition (Single Execution Pipeline)**:
            - Executes across $N_{mut}$ (whether originally purely mutable or a mixed hub that fell through from step 1).
            - Partitions the mutable abstractions outward without disturbing the underlying factual leaves.
     - **Step 3 (Neighbor Edge Re-Wiring & Non-Destructive Invariant)**:
       - Deletes direct edges from $H$ to rewired neighbors, connecting them to the new sub-concepts with new sub-concepts linked to $H$ via `SUBSET_OF`.
       - The parent hub $H$ is **never deleted**, preserving the hierarchical anchor of the tree.
   - Because intra-document nodes are immutable and graph partitions are mutually exclusive, persona updates proceed completely independently without conflicts.

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

### Speech-to-Text (STT) Voice Dictation
- **In-Browser Whisper Model**: Speech is captured via `MediaRecorder` (Opus) and transcribed 100% locally using `@xenova/transformers` (`Xenova/whisper-base.en`) running on WebAssembly/WebGPU.
- **Editable Draft Workflow**: Stopping voice recording places the transcribed text directly into the chat input textarea without auto-sending. Users can review, adjust technical terms, and fix typos before manually submitting via `Enter` or the `Send` button.
- **Clean Input Reset**: Submitting the form resets the textarea immediately for the next interaction.

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

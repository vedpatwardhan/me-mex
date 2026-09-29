# Master Technical Report: Agentic Knowledge Graph Architecture, Retrieval-First User Flow, Universal Storage Primitive, and Complete Literature Synthesis

**Date:** September 22, 2026  
**Author:** Antigravity AI & Cortex-OS Team  
**Target Architecture:** Graph-Memex (`me-mex`) & Cortex Knowledge Engine  
**File Location:** `docs/reports/2026-09-22_agentic_graph_user_flow_synthesis.md`

---

## Executive Summary

This report provides the exhaustive technical blueprint for the **Graph-Memex (`me-mex`) Knowledge Engine**. It unifies our end-to-end operational user flows (Retrieval-First exploration, conversational graph editing, real-time visual canvas animation, user-triggered commits, and human-in-the-loop multi-agent debate) with a clean, low-clutter storage model.

It incorporates full theoretical literature mappings from all eight surveyed frameworks: **Microsoft GraphRAG**, **OSU HippoRAG 2**, **HKU LightRAG**, **Zep / Graphiti**, **A-MEM**, **fastbmRAG**, **Stanford STORM**, and **Google AI Co-Scientist**.

---

### 1. Unified Concept Hub Persona Architecture

Both **Retrieval** and **Ingestion** operate on a single conversational gateway (`POST /api/chat`) structured around **Dynamic Concept Hub Personas**:

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
    (Sub-graph traversal & search)                  (Sub-graph traversal & search)
 2. Relevance Debate                             2. Relevance Debate
    (Relevance to prompt & query)                   (Relevance to prompt & query)
 3. Persona Synthesis                            3. Multi-Persona Merging Debate
    (Answer generation & glows)                     (Evaluates extracted concepts against
                                                     local hub knowledge, decides node 
                                                     updates, edge creation & topology additions)
```

### The Unified 3-Step Persona Workflow

1. **Shared Multi-Hop Sub-Graph Exploration (Common to Retrieval & Ingestion):**
   - The Executive Orchestrator evaluates the user prompt, full conversation history (`chat_history`), system events, and active workspace context (`project_id`).
   - `rustworkx` centrality identifies top project-scoped concept hubs ("Department Offices").
   - **Iterative Multi-Hop Traversal**: Each concept hub persona iteratively expands its frontier up to a maximum depth (`max_depth = 3`). At each hop, candidate unvisited neighbor nodes are evaluated by the persona to decide which nodes are relevant and worth exploring deeper to build full domain context.
   - **Root Media Traversal Blocking**: Traversal visits Root Media nodes (`paper`, `blog`, `video`, `post`) for textual description/provenance context, but strictly **blocks Root Media nodes from expanding further hops** (preventing artificial shortcutting like $Concept_A \rightarrow Paper_D \rightarrow Concept_E$).

2. **Relevance Debate (Common to Retrieval & Ingestion):**
   - Each Specialist Persona debates the relevance of its accumulated multi-hop sub-graph context against the user prompt and current chat context.
   - **In Retrieval Mode:** The debate determines how closely the explored multi-hop sub-graph relates to the query topic, emitting glowing `traversed_node_ids` to the WebGL visualizer and providing grounded evidence to the Orchestrator for synthesis.

3. **Multi-Persona Concept Merging Debate (Ingestion Specific Step):**
   - Ingestion adds an explicit **Concept Merging Debate Step** on top of shared exploration and relevance debate.
   - **Document-Level Consolidation**: Passage-level concepts extracted from the incoming document are first consolidated into a set of document-specific canonical concepts (`consolidate_extracted_concepts`).
   - **Persona Knowledge Base**: Each persona treats its hub and adjacent neighborhood as its specialized knowledge base (*"Everything I know about this domain in the database"*).
   - **Ingestion Merging Evaluation**: All consolidated concepts from the document are passed to every relevant concept hub persona to merge them into the global graph topology.
   - **Per-Persona Graph Integration:** Each persona independently evaluates the document's concepts against its domain knowledge:
     - **Inclusion & Merging:** Decides whether a concept should be merged into an existing node, updated with new text, or instantiated as a new concept.
     - **Multi-Hub Connection (Multiple Edges):** If a single concept from the document is relevant to multiple concept hub personas, each persona creates its own connection edges (`GraphEdge`), naturally attaching the concept to multiple hubs across the graph.
     - **Decomposition:** Personas break down high-level or compound concepts into lower-level atomic components if necessary for clean domain alignment.

---

## 2. Concept Hub Detection & Incremental Macro Document Maintenance

To avoid re-generating macro documents across the entire corpus after every single ingestion pass, the engine uses **Concept Hub Detection** and **Incremental Delta Patching**.

```
[New Paper Ingested] ──> [Identifies Affected Concept Hubs]
                                    │
                                    ▼
                [Patch ONLY Affected Department Macro Document]
                (Leaves all other 3 Macro Documents untouched)
```

### A. How Concept Hubs (Departments) Are Detected

Concept Hubs represent high-degree thematic clusters in the graph network. They are detected using Python graph analytics (`rustworkx` / `NetworkX` in memory):

1. **Degree Centrality:** `CONCEPT` nodes connected to $\ge 10$ papers or sub-concepts are classified as **Primary Concept Hubs** (e.g. *World Models*, *Flow Matching*).
2. **Leiden Community Partitioning (GraphRAG Principle):** Running the Leiden community detection algorithm on the concept adjacency network partitions all concepts into 3 to 4 distinct **Thematic Departments**. Each community forms one Department Macro Document.

### B. Incremental Delta Macro Patching

When a new paper is merged:
1. **Scope Localization:** The engine checks which Leiden Community / Concept Hub the new concepts belong to (e.g. *Department 2: World Models*).
2. **Targeted Macro Update:** Only the Macro Document for *Department 2* undergoes an incremental LLM patch summarizing the new addition. The other Macro Documents remain untouched, keeping token costs low and execution speed under 2 seconds.

---

## 3. Interactive Pre-Ingestion Graph Exploration & Conversational Link Editing

Users can query, critique, and edit the existing graph visualizer purely through natural language chat **before doing any document ingestion** ("playing around with the graph"):

```
[User Exploratory Query] ──> [Persona Search Retrieves Seed Nodes]
                                        │
                                        ▼
                  [User Critique: "Why didn't you link X and Y?"]
                                        │
                                        ▼
           [User Command: "Introduce a link between X and Y because..."]
                                        │
                                        ▼
             [Agent Instantiates CONNECTION_EDGE Node in Real Time]
```

1. **Seed Concept Retrieval:** Based on conversational context, the Specialist Personas retrieve seed concept nodes and traverse connected paths.
2. **Conversational Critique:** The user challenges the retrieved context (*"What about this older paper? Why didn't you include its connection to latent world models?"*).
3. **Conversational Graph Editing:** The user instructs the LLM: *"Introduce a link between Paper X and Concept Y, given that they both use flow matching for action decoding."*
4. **On-the-Fly Node Mutation:** The agent immediately creates or updates a `CONNECTION_EDGE` node with the user's rationale (`description: "both use flow matching for action decoding"`). The WebGL visualizer updates instantly to render the new link on screen.

---

## 4. Persona-Driven Retrieval over Arbitrary Graph Depth

### Why Pure Vector Embeddings Fail at Graph Depth
Standard vector embeddings rely on surface-level cosine distance in static 1536-D space. They fail at graph depth because:
1. They cannot perform **relational multi-step deduction** (*"Find papers that refute the reward formulation of LeWM"*).
2. Distance metrics degrade rapidly across multi-hop paths.
3. They treat facts as flat text without understanding topological relationships.

### The Persona-Driven Retrieval Solution

```
[User Query / New Paper Preview]
                │
                ▼
[Stage 1: Global Registry Persona Scan]
(Scans 3-4 Compressed Global Registry Documents -> Identifies Target Domains)
                │
                ▼
[Stage 2: Specialist Persona Subgraph Traversal & Debate]
(Domain Personas traverse structural edges [BUILDS_UPON, CONTRASTS] & debate relevance)
(Visual Graph Canvas animates/glows explored nodes in real-time)
                │
                ▼
[Stage 3: Grounded Retrieval Consensus]
(Returns top subgraphs + plain text passage pointers for chat & merge preparation)
```

---

## 5. Simplified Storage Model & Universal Node Primitive

### Graph Topology Rule: Zero Passage Clutter

Passage text chunks are **NOT** graph nodes in the database network or UI visualization.

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

### Universal Node Schema & Out-of-Graph Passage Grounding

```
+-----------------------------------------------------------------------------------+
|                           Universal Node Document Schema                          |
|                                                                                   |
|  - id: String (snake_case / UUID)                                                 |
|  - node_class: Enum (ROOT_MEDIA | CONCEPT | CONNECTION_EDGE)                       |
|  - title: String                                                                  |
|  - description: Markdown (Atomic self-evolving description & synthesis)             |
|  - metadata: JSON (Source URL, dates, authors, tags, status)                      |
|  - embedding_vector: Float[1536] (Dense semantic representation)                  |
|  - passage_ids: List[PassageID] (Out-of-graph plain text chunk references)   |
+-----------------------------------------------------------------------------------+
```

---

## 6. Reference Case Study: Robotics World Models (Pixel vs. Latent Space)

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

### Dynamic Edge Weight Decay & Link Propagation
1. **Parallel Link Propagation:** When a downstream task concept (*Action Planning via MPC*) is linked to an older paradigm (`Pixel-Space World Models`), the engine infers/proposes a parallel connection to the newer paradigm (`Latent-Space World Models`).
2. **Dynamic Weight Decay (No Deletion):**
   - **New SOTA Link:** Instantiated with `weight: 1.0` and `status: "PRIMARY_ACTIVE"`.
   - **Legacy Link:** Retained with `weight: 0.3` and `status: "HISTORICAL_SUPERSEDED"`.

---

## 7. Managing Outdated & Superseded Knowledge

1. **Option A (Recommended - Status Tagging & Weight Decay):** `CONNECTION_EDGE` nodes carry a `status` (`PRIMARY_ACTIVE`, `HISTORICAL_SUPERSEDED`) and numeric `weight` ($1.0 \rightarrow 0.3$).
2. **Option B (Concept Revision History):** `CONCEPT` nodes maintain an internal `revision_history` array recording prior text body summaries before evolution passes.
3. **Option C (Lightweight Bi-Temporal Metadata):** Attach `valid_from` and `valid_to` timestamps to `CONNECTION_EDGE` nodes.

---

## 8. Comprehensive Synthesis & Taxonomy Matrix of All Surveyed Literature

| Paper / Framework | Primary Specialty | Core Schema Primitive | Primary Search / Retrieval Mechanism | Role & Adaptation in Graph-Memex (`me-mex`) |
| :--- | :--- | :--- | :--- | :--- |
| **Microsoft GraphRAG** | Global Sense-Making & QFS | Entity Records + Hierarchical Leiden Community Reports | Map-Reduce Summaries over Community Reports | Powers **Compressed Global Registry Documents** (Macro-level maps) & Leiden Hub partitioning. |
| **OSU HippoRAG 2** | Deep Multi-Hop Associative Recall | Dual-Node Graph (Passage Nodes + Phrase Nodes) | Joint Vector-Graph Personalized PageRank (PPR) | Inspires **Out-of-Graph Passage Grounding** (`CONCEPT` $\rightarrow$ Passage ID pointers) & PPR traversal. |
| **HKU LightRAG** | Low-Cost Incremental Ingestion | Entity Profiles & Relationship Key-Value Profiles | Dual-Level (Low-Level Entity + High-Level Relation) KV Search | Enables **instant, low-cost paper intake** without global Leiden re-clustering. |
| **Zep / Graphiti** | Temporal Agent Memory & Invalidation | Bi-Temporal Graph ($T_{valid}, T_{trans}$) | Hybrid Vector + Keyword + Temporal Edge Filter | Informs **Dynamic Edge Weight Decay** (`weight: 1.0` $\rightarrow$ `0.3`) for paradigm shifts. |
| **A-MEM** | Self-Evolving Note Memory | Atomic Zettelkasten Notes with Dynamic Link Keys | Multi-attribute vector similarity + retroactive link updates | Drives **Self-Evolving Concept Notes**, updating concept summaries as new papers merge. |
| **fastbmRAG** | Biomedical Full-Text Ingestion | Two-Stage Draft (Abstract) vs. Refined (Body) Graph | Abstract Graph Drafting + Vector Entity Linking | Powers the **Multi-Level Granularity Pipeline** (Abstract drafting $\rightarrow$ passage-linked concept refining). |
| **Stanford STORM** | Perspective-Guided Synthesis | Expert Persona Interview Transcripts & Outlines | Simulated Persona Interviews over Information Trees | Inspires **Phase 1 Exploratory Chat & Persona Retrieval**. |
| **Google AI Co-Scientist** | Automated Scientific Hypothesis Loop | Pairwise Tournament Hypotheses & Meta-Reviews | Multi-Agent Reflection Loops & Elo Tournaments | Powers **Phase 4 Multi-Agent Persona Debate with Human-in-the-Loop**. |

---

## 9. Technical Implementation Stack & Database Engine Feasibility

### A. Database Choice: MongoDB Document Engine (No Neo4j)
- Partitioned across `themes`, `nodes` (`ROOT_MEDIA`, `CONCEPT`), and `edges` (`CONNECTION_EDGE`) collections.
- Shallow traversals ($\le 2$ hops) via `$graphLookup`; vector search via `$vectorSearch` HNSW indexes.
- Deep graph algorithms (PageRank, Leiden hub partitioning) run in Python memory via `rustworkx` / `scipy.sparse`.

### B. FastMCP & Bidirectional Markdown Synchronization
- FastMCP protocol exposes atomic graph tools via Python `fastmcp`.
- Markdown sync engine keeps local Markdown files (`deeper_read_notes.md`, `overall_insights.md`, `select_papers.md`) 100% synchronized with MongoDB via `watchdog` listeners and AST parsers.

---

## 10. Master Architectural Commitments

1. **Unified Department / Persona Architecture:** A single multi-agent pattern where Compressed Macro Documents define "Department Offices", Department Sub-Agents explore their subgraphs, and Executive Orchestrators handle retrieval synthesis or ingestion merge.
2. **Concept Hub Detection & Delta Macro Patching:** Python graph analytics (`rustworkx` degree centrality + Leiden community partitioning) identify concept hubs. Ingesting new papers updates ONLY the affected Department's Macro Document.
3. **Conversational Pre-Ingestion Graph Editing:** Users can query, critique, and add custom connections between nodes purely through natural language chat while exploring existing subgraphs.
4. **Clean 3-Element Topology:** Nodes are strictly `ROOT_MEDIA`, `CONCEPT`, and `CONNECTION_EDGE`. Passages are plain text database records referenced by ID pointers.
5. **Dynamic Edge Weight Decay:** Paradigm shifts decay historical edge weights (`1.0` $\rightarrow$ `0.3`) without deleting legacy provenance.

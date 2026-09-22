# Project Specification: Graph-Memex (Agentic Knowledge Graph & Multi-Modal Intake Engine)

> **Document Purpose**: This document defines the master specification for **Graph-Memex (`me-mex`)**, unifying the project's core research use case with our agentic retrieval-first architecture, clean 3-element graph topology, universal node schema, and human-in-the-loop multi-agent debate engine.

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

Graph-Memex operates on a continuous **Retrieval $\rightarrow$ Exploration & Editing $\rightarrow$ Ingestion & Macro Update $\rightarrow$ Retrieval** loop.

```
       ┌──────────────────────────────────────────────────────────┐
       │                [User Query / New Paper Link]             │
       └────────────────────────────┬─────────────────────────────┘
                                    │
                                    ▼
       [PHASE 1: RETRIEVAL VIA GLOBAL REGISTRY & PERSONA SEARCH]
       - Global Registry Persona scans 3-4 Compressed Macro Documents
       - Specialist Personas traverse structural edges (BUILDS_UPON, CONTRASTS)
       - Persona debate determines true relevance over pure vector distance
       - Visual canvas glows/animates candidate nodes in real-time
                                    │
                                    ▼
       [PHASE 2: CONVERSATIONAL EXPLORATION & MANUAL GRAPH EDITING]
       - Staged Sandbox: Uploaded documents do NOT auto-populate into graph
       - User chats via voice/text to explore subgraphs & staged paper
       - User can critique search results & issue natural language graph edit commands
       - Agent creates/updates CONNECTION_EDGE nodes in real time
                                    │
                                    ▼
       [PHASE 3: USER-TRIGGERED "INTEGRATE INTO GRAPH"]
       - User explicitly triggers merge pipeline when satisfied with understanding
                                    │
                                    ▼
       [PHASE 4: MULTI-AGENT PERSONA DEBATE & MACRO DOCUMENT UPDATE]
       - Seed personas & new paper persona debate merge updates & edge decay
       - System prompts user in chat for input on ambiguous trade-offs
       - Commits node/edge updates to MongoDB & auto-updates Macro Registry Documents
```

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

### Universal Node Schema & Out-of-Graph Passage Grounding

Every entity in the graph network adheres to a single universal node schema. Passages exist purely as plain text database records referenced via ID pointers inside atomic concept notes:

```json
{
  "id": "concept_latent_world_models",
  "node_class": "CONCEPT",
  "title": "Latent-Space World Models",
  "text_body": "Atomic self-evolving Markdown description & synthesis across papers...",
  "metadata": {
    "theme_id": "vla_research",
    "domain_tags": ["world_models", "latent_dynamics"],
    "status": "PRIMARY_ACTIVE"
  },
  "embedding_vector": [0.012, -0.045, 0.891],
  "passage_pointers": ["pass_chunk_101", "pass_chunk_102"]
}
```

#### Role of Out-of-Graph Passage Pointers
1. **User Verification:** When a user clicks a `CONCEPT` node in the UI, it displays the self-evolving concept summary. Clicking a passage ID pointer fetches the raw plain text passage chunk for manual verification.
2. **Agent Debate Grounding:** During the *LLM Conference Debate* merge pass, LLM agents pull up raw plain text passages by ID to ground merge decisions without cluttering the graph topology.

---

## 5. Persona-Driven Retrieval & Compressed Global Registries

### Why Pure Vector Embeddings Fail at Graph Depth
Standard vector embeddings rely on surface-level cosine distance in static 1536-D space. They fail at arbitrary graph depth because they cannot perform relational multi-step deduction (*"Find papers that refute the reward formulation of LeWM"*), and semantic distance metrics degrade over multi-hop paths.

### Persona-Driven Retrieval Engine
1. **Global Compressed Registries (3–4 Macro Documents):**
   - Synthesizes the entire graph into 3–4 high-level thematic maps (the automated equivalent of master index files like `overall_insights.md`).
   - Fits easily inside LLM context windows, allowing instant macro-level domain routing regardless of total graph size.
2. **Specialist Persona Search Discourse:**
   - **Domain Specialist Personas** traverse actual structural relationships (`BUILDS_UPON`, `CONTRASTS_WITH`, `SUPERSEDES`).
   - Personas debate relevance in the background (*"Persona A argues Paper X is relevant due to flow matching; Persona B notes Paper Y is more relevant due to closed-loop MPC"*).
3. **Live Canvas Animation Sync:**
   - As personas traverse and debate candidates, the WebGL graph visualizer (`react-force-graph`) animates in real time, glowing candidate nodes (`traversingNodeIds`).

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
   - PageRank (HippoRAG) prioritizes `weight: 1.0` paths during daily reviews while preserving full historical lineage.

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
 - Explores relevant subgraphs                   - Debates concept merging & new nodes
 - Synthesizes retrieved context                 - Adjusts edge weights (1.0 -> 0.3)
 - Animates visual graph canvas                  - Incrementally patches affected Macro
```

### Concept Hub Detection & Incremental Delta Patching
To avoid re-generating macro documents across the entire corpus after every single ingestion pass:
1. **Hub Detection:** Python graph analytics (`rustworkx` degree centrality + Leiden community partitioning) identify primary concept hubs (concepts connected to $\ge 10$ nodes) and group them into 3 to 4 Department Communities.
2. **Incremental Delta Patching:** When a new paper is merged into Department 2 (*World Models*), a background Macro Synthesis Agent updates **ONLY the Department 2 Macro Document**. The other 3 Macro Documents remain untouched, keeping token costs near-zero and execution speed under 2 seconds.

---

## 8. Technology Stack & Technical Constraints

### A. Database Choice: MongoDB Document Engine (No Neo4j)
- **Constraint**: Do **NOT** use Neo4j.
- **Storage Model**: **MongoDB** document database.
  - Data partitioned across `themes`, `nodes` (`ROOT_MEDIA`, `CONCEPT`), and `edges` (`CONNECTION_EDGE`) collections.
  - Adjacency traversals ($\le 2$ hops) via `$graphLookup` aggregation pipelines.
  - Integrated MongoDB Vector Search (`$vectorSearch` HNSW indexes) for initial candidate retrieval.
  - Deep graph algorithms (PageRank, Leiden hub partitioning) run in Python memory via `rustworkx` or `scipy.sparse`.

### B. FastMCP Protocol & Bidirectional Markdown Sync
- **FastMCP Protocol**: Exposes atomic graph tools (`add_paper_node`, `connect_nodes`, `query_neighborhood`, `patch_macro_document`) via Python `fastmcp`.
- **Bidirectional Sync Engine**: Keeps local Markdown files (`deeper_read_notes.md`, `overall_insights.md`, `select_papers.md`) 100% synchronized with MongoDB via `watchdog` file listeners, python-markdown AST parsers, and SHA-256 version hash validation.

### C. WebGL Frontend Visualizer
- Modern React WebGL visualizer (`react-force-graph-2d`) with custom canvas node styling, live traversal glow animations (`traversingNodeIds`), stationary camera controls on node selection, and side Markdown detail drawer.

---

## 9. Implementation Phasing

- **Phase 1**: MongoDB Document Schema, FastMCP Server, & Bidirectional Markdown Sync Engine.
- **Phase 2**: React + WebGL Canvas (`react-force-graph`) with Live Traversal Glow, Stationary Node Selection, & Markdown Side Drawer.
- **Phase 3**: Retrieval-First Engine with Compressed Global Registries & Specialist Persona Search.
- **Phase 4**: User-Triggered Ingestion Pipeline with Staged Conversational Sandbox, Human-in-the-Loop Multi-Agent Debate, & Incremental Delta Macro Patching.

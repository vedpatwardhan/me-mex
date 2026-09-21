# Graph-Memex (`me-mex`) Architecture & Prototype Roadmap

**Date:** 2026-09-20  
**Status:** Strategic Blueprint & Implementation Roadmap  
**Target Directory:** [`me-mex/`](file:///Users/vedpatwardhan/Desktop/cortex-os/me-mex)  

---

## 1. Executive Summary & Core Philosophy

**Graph-Memex (`me-mex`)** is a local-first, interactive visual knowledge graph and autonomous ideation engine designed for high-throughput literature synthesis, associative recall, and scientific discovery. 

Rather than building backend schemas first and guessing interaction patterns, **Graph-Memex follows a UI-First, Build-Back Paradigm**. Designing user interaction flows first clarifies node granularity, mutation patterns, ephemerality vs. persistence, and schema requirements before locking down backend MongoDB pipelines.

---

## 2. The 3-Pane UI Interaction Model

The interface specification forms the core contract driving all data structures and backend services:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               GRAPH-MEMEX INTERACTION CANVAS                           │
├─────────────────────────┬───────────────────────────────┬──────────────────────────────┤
│ 1. SCRATCHPAD & INBOX   │ 2. FORCE GRAPH CANVAS         │ 3. SLIDE-OUT MARKDOWN DRAWER │
│    (Agent Activity)     │    (react-force-graph)        │    (Reader & Editor)         │
├─────────────────────────┼───────────────────────────────┼──────────────────────────────┤
│ [Active Intake Feed]    │  (Category Hub: VLA)          │ # Paper Title                │
│ • Paper X ingested      │       /       \               │                              │
│ • Proposed Links (2)    │      /         \              │ **2-Line Takeaway**          │
│   - [Accept] [Reject]   │ [Paper A] === [Paper B]       │ Compact factual summary...   │
│                         │     \           /             │                              │
│ [Curriculum Review]     │      \         /              │ **Connections**              │
│ • Due Today: 12 nodes   │    [Deep Lesson Hub]          │ -> Builds upon [Paper A]     │
│   [Start 15m Session]   │                               │ -> Contrasts with [Paper C]  │
│                         │ Physics:                      │                              │
│ [Idea Tournament]       │ • Solid: Strong mesh links    │ **Detailed Notes / AST**     │
│ • Top Elo Hypotheses    │ • Dashed: Weak umbrellas      │ Interactive body text...     │
└─────────────────────────┴───────────────────────────────┴──────────────────────────────┘
```

1. **Pane 1: Scratchpad / Proposal Inbox (Left Rail)**
   - Serves as the staging area. Agents propose link mutations, hypothesis dossiers, and paper ingests for human approval (`[Accept] / [Reject]`).
   - Hosts the daily spaced repetition queue (**FSRS-DAG**) for targeted <15-minute node reviews.
2. **Pane 2: Main Force Canvas (Center View)**
   - Built on `react-force-graph`.
   - Visualizes decoupled physics: strong mesh lines pull closely related papers into tight visual clusters, while weak structural topic links render as dashed splines.
   - Clicking nodes highlights $k$-hop neighborhoods and loads Pane 3.
3. **Pane 3: Markdown Reader & Quick Editor (Right Slide-Out Drawer)**
   - Displays the note's parsed Markdown AST, executive 2-line takeaways, wiki-links, and categories.
   - Enables direct inline editing and manual connection creation.

---

## 3. The 4-Milestone Prototype Roadmap

```
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │                        THE 4-MILESTONE PROTOTYPE ROADMAP                               │
 └────────────────────────────────────────────────────────────────────────────────────────┘

  [ Milestone 1: Visual Scratchpad & Interactive Graph UI (Frontend-First) ]
   ├── Scaffold Next.js / Vite client using react-force-graph-2d
   ├── Mock JSON dataset (10–15 papers, 2 categories, explicit edges)
   ├── Slide-out Markdown drawer (Vaul / CSS transition drawer) for reading & editing
   └── Scratchpad view showing real-time agent proposals and user confirmation toggles

  [ Milestone 2: Local Ground Truth & Data Plane (File & DB Sync) ]
   ├── 100% sync between Markdown files & MongoDB collections (watchdog AST + Change Streams)
   ├── Pydantic / BAML schema validation for nodes and edges
   └── FastMCP tool service exposing basic CRUD, vector search, and local hops ($graphLookup)

  [ Milestone 3: High-Speed Intake & Topological Associative Retrieval ]
   ├── fastbmRAG two-stage ingestion (abstracts in deeper_read_notes -> main text in select_papers)
   ├── HippoRAG 2 dual-node graph (Passages + Phrases) with joint vector-PPR search in memory
   └── PaperQA2 RCS (Reranking Contextual Summarization) evidence filter before generation

  [ Milestone 4: Autonomous Ideation, Dynamic Evolution & Spaced Repetition ]
   ├── Google Co-Scientist tournament loops: Generation, Reflection (falsification), Ranking (Elo)
   ├── A-MEM retroactive note evolution updating overall_insights.md takeaways
   ├── Graphiti bi-temporal invalidation (valid_time vs. transaction_time)
   └── FSRS-DAG morning briefing queue for targeted <15-minute reviews
```

---

## 4. Scientific Literature & Framework Alignment

No single research paper covers the complete lifecycle. The literature aligns across four specialized functional tiers:

| Functional Tier | Target Papers / Frameworks | Specific Role in Graph-Memex |
| :--- | :--- | :--- |
| **1. Intake & Streaming** | **fastbmRAG**, **LightRAG**, **Cognee** | Abstract-first drafting into `deeper_read_notes` before main-text parsing; Key-Value entity profiling; Extract-Cognify-Load (ECL) schemas. |
| **2. Memory & Substrate** | **HippoRAG 2**, **A-MEM**, **Graphiti**, **MongoDB** | Dual-node graph (Passages vs. Phrases); Zettelkasten atomic note evolution; bi-temporal edge invalidation (`valid_time` vs `transaction_time`). |
| **3. Search & Evidence Audit** | **HippoRAG 2**, **PaperQA2**, **ScientistOne** | Joint Vector + Personalized PageRank (PPR) multi-hop recall; Reranking Contextual Summarization (RCS) token filtering; Chain-of-Evidence (CoE) provenance. |
| **4. Ideation & Evolution** | **Google Co-Scientist**, **STORM**, **EvoFSM**, **py-fsrs** | Assumption decomposition, hostile reflection (falsification), pairwise Elo tournaments, perspective-driven self-play, and FSRS morning review queues. |

---

## 5. Architectural Data Transformation Flow (Co-Scientist Paradigm)

Data progresses through five distinct transformation levels across its lifecycle:

```
                                  [ Human Scientist ]
                                           │
                                           │ (Goal, Scope, Constraints)
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ LEVEL 0: RAW STREAMING INTAKE & DISCOVERY (Short-Form Ephemeral Working Buffers)       │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ Web / Scholarly APIs ──Tool Call──> Micro-read chunk / Extract claim ──> Self-Play     │
└────────────────────────────────────────────────┬───────────────────────────────────────┘
                                                 │ Compiled & Structured
                                                 ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ LEVEL 1: STRUCTURED HYPOTHESIS ARTIFACT (Medium-Form Standardized Dossier, ~1-2k Toks) │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ Hypothesis Dossier: Title, Mechanistic Rationale, Sub-Assumptions, Provenance Ledger   │
└────────────────────────────────────────────────┬───────────────────────────────────────┘
                                                 │ Broadcast to Audit & Arena
                                                 ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ LEVEL 2: VALIDATION, DIVERSIFICATION & MATCH PLAY (Medium-Form Audit Records)          │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ Proximity Space Matrix (Vector) ── Reflection Logs (Falsification) ── Pairwise Elo Arena│
└────────────────────────────────────────────────┬───────────────────────────────────────┘
                                                 │ Evaluated & Ranked
                                                 ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ LEVEL 3: PERSISTENT TOURNAMENT LEDGER & EVOLUTION (Long-Form Consolidated State)       │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ Dynamic Elo Leaderboard ── Falsified Archive ── Evolution Agent (Parent Selection)     │
└────────────────────────────────────────────────┬───────────────────────────────────────┘
                                                 │ Distillation / Synthesis
                                                 ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ LEVEL 4: SYSTEMIC KNOWLEDGE COMPACTION (Permanent Macro Insights)                      │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ Meta-Review Executive Briefs ("Learning Without Backprop") -> Injected into Memory     │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Strategic Framework Decisions

### 6.1 OpenClaw Deferred to Phase 5
* **Role:** OpenClaw is an operational gateway and multi-channel runtime (WhatsApp, Telegram, Discord, `SKILL.md` execution).
* **Verdict:** **Defer to Phase 5.** The immediate priority for Milestones 1–4 is graph topology, bidirectional Markdown-to-MongoDB synchronization, and associative discovery. FastMCP provides the necessary typed RPC layer for IDE integration without daemon overhead.

### 6.2 Core Technical Constraints
* **Storage:** Local-first MongoDB (no Neo4j dependency).
* **RPC / Tooling:** FastMCP server exposing graph tools to Cursor/Claude agents.
* **Extraction Model:** Open-weight LLMs (e.g., Ministral 3 8B / Ollama / local inference) for cost-effective background chunking and extraction.

---

## 7. Workspace Documentation Synchronization Plan

To align the entire workspace documentation with this roadmap, update the following files:

1. [`docs/general_architecture_overview.md`](file:///Users/vedpatwardhan/Desktop/cortex-os/me-mex/general_literature_review.md): Add the 5-level Co-Scientist data transformation flow and the dual-node PageRank traversal engine.
2. [`README.md`](file:///Users/vedpatwardhan/Desktop/cortex-os/me-mex/README.md): Structure around the 4 UI-first milestones and technical constraints.
3. [`select_papers.md`](file:///Users/vedpatwardhan/Desktop/cortex-os/me-mex/select_papers.md): Add explicit functional tier assignments (Intake, Substrate, Search, Ideation) to each paper summary.
4. [`multi_agent_literature_review.md`](file:///Users/vedpatwardhan/Desktop/cortex-os/me-mex/multi_agent_literature_review.md): Reclassify OpenClaw as an operational gateway target for Phase 5.

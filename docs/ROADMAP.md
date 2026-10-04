# Me-Mex Architecture & Implementation Roadmap

> **Document Purpose**: This document outlines the strategic implementation roadmap, UI-first interaction paradigm, and 4-milestone execution plan for **Me-Mex**.

---

## 1. Executive Summary & Core Philosophy

**Me-Mex** is a local-first, interactive visual knowledge graph designed as an external memory system for textual knowledge synthesis (academic research papers, technical blogs, YouTube transcripts), associative recall, and scientific discovery.

Rather than building backend schemas first and guessing interaction patterns, **Me-Mex follows a UI-First, Build-Back Paradigm**. Designing user interaction flows first clarifies node granularity, mutation patterns, ephemerality vs. persistence, and schema requirements before locking down backend MongoDB pipelines.

---

## 2. The 3-Pane UI Interaction Model

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

1. **Pane 1: Scratchpad / Proposal Inbox (Left Rail)**: Serves as the staging area where agents propose link mutations and paper ingests for human approval (`[Accept] / [Reject]`).
2. **Pane 2: Main Force Canvas (Center View)**: Visualizes decoupled physics using `react-force-graph-2d`, where strong mesh lines pull related concepts into tight visual clusters.
3. **Pane 3: Markdown Reader & Quick Editor (Right Slide-Out Drawer)**: Displays parsed Markdown AST, executive takeaways, wiki-links, and passage references with inline editing capabilities.

---

## 3. The 4-Milestone Prototype Roadmap

```
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │                        THE 4-MILESTONE PROTOTYPE ROADMAP                               │
 └────────────────────────────────────────────────────────────────────────────────────────┘

  [ Milestone 1: Visual Scratchpad & Interactive Graph UI (Frontend-First) ] — COMPLETED
   ├── Scaffold Vite client using react-force-graph-2d
   ├── Slide-out Markdown drawer for reading & editing
   └── Scratchpad view showing real-time agent proposals and user confirmation toggles

  [ Milestone 2: Local Ground Truth & Data Plane (File & DB Sync) ] — COMPLETED
   ├── 100% sync between Markdown files & MongoDB collections (MongoDB / In-Memory store)
   ├── Pydantic schema validation for GraphNode and GraphEdge entities
   └── FastMCP tool service exposing basic CRUD, vector search, and local hops ($graphLookup)

  [ Milestone 3: High-Speed Intake & Topological Associative Retrieval ] — COMPLETED
   ├── Zero-mutation ingestion pipeline with out-of-graph PassageRecord storage
   ├── Mutually exclusive concept hub exploration via rustworkx eigenvector centrality
   └── Independent persona sub-graph reorganization & passage-grounded concept splitting

  [ Milestone 4: Autonomous Ideation, Dynamic Evolution & Spaced Repetition ] — IN PROGRESS
   ├── Tournament loops: Generation, Reflection (falsification), Ranking (Elo)
   ├── Dynamic node evolution updating overall_insights.md takeaways
   └── FSRS-DAG morning briefing queue for targeted <15-minute reviews
```

---

## 4. Scientific Literature & Framework Alignment

| Functional Tier | Target Papers / Frameworks | Specific Role in Graph-Memex |
| :--- | :--- | :--- |
| **1. Intake & Streaming** | **fastbmRAG**, **LightRAG**, **Cognee** | Abstract-first drafting into `deeper_read_notes` before main-text parsing; Key-Value entity profiling; Extract-Cognify-Load (ECL) schemas. |
| **2. Memory & Substrate** | **HippoRAG 2**, **A-MEM**, **Graphiti**, **MongoDB** | Dual-node graph (Passages vs. Phrases); Zettelkasten atomic note evolution; bi-temporal edge invalidation (`valid_time` vs `transaction_time`). |
| **3. Search & Evidence Audit** | **HippoRAG 2**, **PaperQA2**, **ScientistOne** | Joint Vector + Personalized PageRank (PPR) multi-hop recall; Reranking Contextual Summarization (RCS) token filtering; Chain-of-Evidence (CoE) provenance. |
| **4. Ideation & Evolution** | **Google Co-Scientist**, **STORM**, **EvoFSM**, **py-fsrs** | Assumption decomposition, hostile reflection (falsification), pairwise Elo tournaments, perspective-driven self-play, and FSRS morning review queues. |

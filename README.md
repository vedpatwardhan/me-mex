# Graph-Memex (`me-mex`)

> **Agentic Knowledge Graph & Multi-Modal High-Volume Intake Engine**

Graph-Memex (`me-mex`) is an agentic research assistant and personal long-term memory system designed to digest massive streams of multi-modal content—including academic research papers, YouTube transcripts, lecture audio, codebase repositories, and experimental logs—without manual file scrolling or cognitive overload.

---

## 🏗️ The Grand Architecture

The architecture of Graph-Memex is synthesized from 15 state-of-the-art papers across Knowledge Graph RAG, agentic memory, automated scientific discovery, and control systems:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        1. Multi-Modal Ingestion & Intake                               │
└────────────────────────────────────────────────────────────────────────────────────────┘
 - fastbmRAG: Abstract-first drafting (deeper_read_notes.md) -> Main-text refining (select_papers.md).
 - Cognee: Extract-Cognify-Load (ECL) pipeline with Pydantic/BAML structured models.
 - LightRAG: Key-Value profiling & instant incremental writes to MongoDB without re-clustering.

┌────────────────────────────────────────────────────────────────────────────────────────┐
│                       2. Memory Storage & Topological Graph                            │
└────────────────────────────────────────────────────────────────────────────────────────┘
 - A-MEM: Atomic Zettelkasten nodes with multi-attribute tags & retroactive note evolution.
 - Graphiti: Bi-temporal schema (valid_time vs transaction_time) to invalidate outdated facts.
 - HippoRAG 2: Dual-node graph (Passages + Phrase Entities) bridging vector search & graph paths.

┌────────────────────────────────────────────────────────────────────────────────────────┐
│                     3. Search, Retrieval & Evidence Auditing                           │
└────────────────────────────────────────────────────────────────────────────────────────┘
 - HippoRAG 2: Joint Vector + Graph Personalized PageRank (PPR) for deep multi-hop recall.
 - PaperQA2: Reranking Contextual Summarization (RCS) to filter evidence chunks before answering.
 - ScientistOne: Chain-of-Evidence (CoE) hard-linking every claim/metric back to source offsets.

┌────────────────────────────────────────────────────────────────────────────────────────┐
│                   4. Synthesis, Deep Research & Agent Execution                        │
└────────────────────────────────────────────────────────────────────────────────────────┘
 - STORM: Multi-perspective persona interviews & information trees for deep research lessons.
 - Co-Scientist: Asynchronous tournament evolution (Reflection, Ranking, Meta-Review) for insights.
 - EvoFSM: Finite State Machine (FSM) control flow separating Macro Flow from Micro Skills.
 - ARTS: Diagnostic log reasoning (code bug vs flawed hypothesis) for experimental runs.
 - Nested Learning: Multi-timescale continuum context flows (Real-Time -> Ingestion -> Review -> Macro).
```

---

## 📚 Literature Synthesis & Paradigm Mapping

| Paper | Key Innovation | Role in Graph-Memex (`me-mex`) |
| :--- | :--- | :--- |
| **Microsoft GraphRAG** ([2404.16130](https://arxiv.org/abs/2404.16130)) | Hierarchical Leiden community detection & Map-Reduce QFS. | Periodic workspace macro briefings & high-level theme clustering. |
| **OSU HippoRAG** ([2405.14831](https://arxiv.org/abs/2405.14831)) | Artificial neocortex (LLM) + hippocampus (KG) with Personalized PageRank (PPR). | Fast multi-hop associative retrieval across entity nodes. |
| **OSU HippoRAG 2** ([2502.14802](https://arxiv.org/abs/2502.14802)) | Dual-node graph (Passages + Phrases) with joint vector-PPR search. | Primary retrieval engine restoring single-hop factual precision while boosting multi-hop recall (+7%). |
| **HKU LightRAG** ([2410.05779](https://arxiv.org/abs/2410.05779)) | Key-Value entity/relation profiling & dual-level retrieval. | High-speed, low-cost streaming ingestion into MongoDB without global re-clustering. |
| **Zep Graphiti** ([2501.13956](https://arxiv.org/abs/2501.13956)) | Bi-temporal knowledge graph schema ($T_{\text{valid}}, T_{\text{trans}}$). | Non-destructive fact invalidation for time-evolving research findings & experimental logs. |
| **fastbmRAG** ([2511.10014](https://arxiv.org/abs/2511.10014)) | Two-stage Draft-and-Refine graph construction via vector entity linking. | Ingests abstracts into `deeper_read_notes.md` first; refines main text into `select_papers.md` (>10x speedup). |
| **A-MEM** ([2502.12110](https://arxiv.org/abs/2502.12110)) | Zettelkasten atomic notes with retroactive memory evolution loops. | Treats papers/insights as atomic notes; retroactively updates historical category takeaways (`overall_insights.md`). |
| **Cognee** ([2505.24478](https://arxiv.org/abs/2505.24478)) | Extract-Cognify-Load (ECL) pipeline with Pydantic structured output models. | Standardizes backend ingestion & multi-engine persistence (Relational + Vector + Graph). |
| **PaperQA2** ([2409.13740](https://arxiv.org/abs/2409.13740)) | Grobid PDF structuring & Reranking Contextual Summarization (RCS). | FastMCP tool evidence filter: scores & summarizes retrieved chunks before passing context to agent/user. |
| **Stanford STORM** ([2402.14207](https://arxiv.org/abs/2402.14207)) | Pre-writing perspective persona discovery & hierarchical outline curation. | Generates standalone deep research topic curricula (`jepa_deep_dive.md`, `rl_landscape.md`) without redundancy. |
| **Google Co-Scientist** ([2502.18864](https://arxiv.org/abs/2502.18864)) | Multi-agent tournament evolution (Generation, Proximity, Reflection, Ranking). | Background agent loops host Elo-ranked idea tournaments to discover latent research connections. |
| **Nested Learning** ([2512.24695](https://arxiv.org/abs/2512.24695)) | Multi-level nested context flows & continuum memory systems. | 4-tier multi-timescale memory system (Real-Time Context $\rightarrow$ Streaming Intake $\rightarrow$ Associative Review $\rightarrow$ Macro Briefings). |
| **ARTS** ([2606.21891](https://arxiv.org/abs/2606.21891)) | Agentic Reasoning for Tree Search & Test-Time Training (TTT) memory retention. | Diagnostic log reasoning for `EXPERIMENT` nodes (separating transient code bugs from baseline hypothesis flaws). |
| **ScientistOne** ([2605.26340](https://arxiv.org/abs/2605.26340)) | Chain-of-Evidence (CoE) framework & 4 integrity audit checks. | Hard-links every claim, metric, and citation in MongoDB back to raw source text offsets or execution JSON logs. |
| **EvoFSM** ([2601.09465](https://arxiv.org/abs/2601.09465)) | Controllable self-evolution via Finite State Machines (FSM). | Decouples agent workflows into Macroscopic Flow (FSM graph logic) and Microscopic Skill (prompts/tools), saving trajectory priors. |

---

## 🛠️ Technology Stack & Key Constraints

* **Database Engine:** **MongoDB** document database (partitioned by `theme_id` across `nodes`, `edges`, `themes` collections; HNSW `$vectorSearch` + `$graphLookup`). *No Neo4j.*
* **Local Extraction Model:** **Ministral 3 8B** running locally via `vLLM` / `llama-cpp-python`, enforced with Pydantic / JSON Schema grammars (`outlines`).
* **Agent Protocol:** **FastMCP** (Python MCP SDK) exposing typed tools for graph mutations, neighborhood expansion, and evidence filtering.
* **Frontend Visualization:** **React + WebGL** (`react-force-graph`), featuring off-canvas Markdown drawers and dual-density edge styling (solid strong mesh vs. dashed weak structural links).
* **Cognitive Review Engine:** Hybrid **FSRS** (Free Spaced Repetition Scheduler) memory decay tracking combined with **DAG topological scheduling** for 15-minute morning review briefings.

---

## 🚀 Phased Implementation Roadmap

* **Phase 1:** MongoDB Schema Initialization, FastMCP Backend Server, and AST Bidirectional Markdown Sync Engine (`deeper_read_notes.md`, `overall_insights.md`, `select_papers.md`).
* **Phase 2:** Local Ministral 3 8B Ingestion Pipeline with Pydantic structured output models (Cognee ECL) & fastbmRAG draft-and-refine parsing.
* **Phase 3:** Interactive Multi-Theme Web UI with `react-force-graph`, off-canvas Markdown reader drawer, and level-of-detail edge culling.
* **Phase 4:** Agentic connection discovery (Co-Scientist tournaments, A-MEM note evolution), HippoRAG 2 joint vector-graph PPR retrieval, and FSRS-DAG topological morning review queue.

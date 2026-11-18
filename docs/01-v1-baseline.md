# Me-Mex v1 baseline (tag `v1`)

> **Canon:** Product direction for v2 is [00-vision-and-principles.md](./00-vision-and-principles.md). This document describes **what shipped** at tag `v1` and **why** it is not sufficient for the markdown research workflow.

Git tag **`v1`** marks the last commit of the **autonomous agentic graph** era before the v2 spec-driven rebuild. Checkout: `git checkout v1`.

---

## 1. Summary

v1 is a working **agentic knowledge graph**: ingest URLs and files, extract concepts, link into a Genesis-rooted mutable tree, retrieve via multi-hop LLM traversal, and chat over SSE with a force-directed canvas. It validated **MongoDB**, **Ministral on Colab vLLM**, passage storage, and mutability rules.

It does **not** match how you actually research: **catalog at scale**, **optional deep read**, **insights that cite every source at the ROOT**, **talk-first** interaction, or **composable** gist / intra-doc / link / reorg tools.

---

## 2. What v1 does well

- **Multi-source ingestion**: URLs, arXiv, local files → passages → chunk-wise extraction → consolidation into canonical intra-doc concepts (see `app/tools/search_tools.py`, trafilatura, arxiv).
- **Clear mutability split**: Immutable evidence vs mutable hierarchy rooted at Genesis (`Everything`).
- **Rich backend**: `GraphNavigator` Genesis-tree traversal, collective linking, generalization, `SPLIT_CONCEPT` reorg (`MutableTreeIndex`, `ReorgQueue`).
- **Live graph UI**: `react-force-graph-2d`, **stabilized layout** (prewarm + pinned positions; no continuous re-layout on hover/selection), SSE traversal highlights, description panel, browser Whisper dictation into **text** chat.
- **Multi-project**: FastAPI projects API; scoped graphs in Mongo.
- **Tests**: Pytest suite under `backend/tests/`.

Full technical detail: checkout git tag **`v1`** (`docs/ARCHITECTURE.md` on that tag). v2 canon: [README.md](../README.md) and this folder.

---

## 3. Why v1 blocks the target workflow

| Symptom | Root cause in v1 |
|---------|------------------|
| You feel like a **passenger** | `ExecutiveOrchestrator` runs long autonomous chains (subgraph expansion, linking, generalize, reorg) on ingest/retrieve before outcomes are visible. |
| **Too slow** for interactive use | Generative LLM **per hop** in `GraphNavigator` (traces under `backend/logs/llm_traces/.../subgraph_expansion.json`). |
| **Implicit graph mutation** | Chat turns can trigger ingestion and graph changes; summaries are not separated from persistence. |
| **Monolithic ingest** | Paste URL → extract → link → generalize → reorg—not separate **gist**, **intra-doc**, **place**, **reorg** steps. |
| **Hard to sculpt the graph** | No first-class “add node, connect A/B/C, mark ToDo” tools; changes funnel through chat intent routing. |
| **Wrong primary interface** | Scrollable **Global Master Chat**; voice is browser Whisper → text box, not LiveKit + dock + custom fields. |
| **Cognitive mismatch** | Your workflow is **three markdown tiers** (catalog → select_papers → overall_insights); v1 optimizes for automatic hierarchy growth. |
| **Typed relation sprawl** | v1 stores many edge “types” in `description` (`SUBSET_OF`, `RELEVANT_TO`, …); v2 uses **one link kind** plus optional user notes ([03-graph-and-memory.md](./03-graph-and-memory.md) §6). |

---

## 4. Assets that illustrate v1

| Asset | What it shows |
|-------|----------------|
| `assets/101126.png` | Graph after multi-paper ingest |
| `assets/101126_2.png` | Retrieval highlight for a query |

---

## 5. Reuse map for v2

| v1 module | v2 disposition |
|-----------|----------------|
| `search_tools.py`, fetch/extract/trafilatura | **Port** behind fetch helpers for inquiry + intra-doc tools |
| Passage packing, consolidation prompts | **Port** behind **intra-document graph** tool only |
| `app/db.py` Mongo models | **Keep** — graph DB is MongoDB in v2 |
| `graph_navigator.py` traversal ideas | **Replace** autoregressive hops with decision scorer + HITL |
| `reorganize_overclustered_nodes` + `SPLIT_CONCEPT` engine | **Do not port execution** — too slow (heavy generative LLM). v2 **reorg** = **reranker recommendations** (frontier relevance) + approved **topology apply** only |
| `orchestrator.py` intent routing | **Replace** with LangGraph supervisor + explicit tools |
| SSE chat stream, scrollback UI | **Replace** with LiveKit + default recommendations dock |
| Browser Whisper | **Replace** with Whisper-tiny in agent pipeline |

See [08-migration-and-reuse.md](./08-migration-and-reuse.md) for file-level detail.
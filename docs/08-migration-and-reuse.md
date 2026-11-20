# Migration and reuse from v1

> **Canon:** [00-vision-and-principles.md](./00-vision-and-principles.md) §8, §11. **Graph model:** [03-graph-and-memory.md](./03-graph-and-memory.md).

v2 **may evolve** the v1 codebase and **MongoDB** where that saves time—no mandate to carry v1 forward.

### Reuse doctrine (read first)

| Rule | Meaning |
|------|---------|
| **v2 spec wins** | `me-mex/docs/` is authoritative. Tag **`v1`** is archaeology, not a port checklist. |
| **Reuse is optional** | Pull from v1 **only when** it clearly matches v2 (composable tools, HITL, DecisionScorer routing, dock/LiveKit UX, etc.). |
| **Do not inherit misalignment** | Skip v1 paths that embody monolithic ingest, auto link/reorg, generative BFS hops, scrollback-as-workspace, or other behavior v2 forbids—even if they “exist and work.” |
| **Rewrite beats wrap** | If v1 structure fights v2 agents/tools, **reimplement** against spec; don’t layer v2 on v1 orchestration. |

Sections below are **candidate** reuse (fetch, passages, canvas layout, prompts)—each item stands on usefulness, not obligation.

---

## 1. Tag boundary

| Artifact | Role |
|----------|------|
| Git tag **`v1`** | Reference implementation + behavior to avoid |
| `main` (or `v2` branch) | Implementation reads `me-mex/docs/` |

`git checkout v1` to inspect autonomous stack: [01-v1-baseline.md](./01-v1-baseline.md).

---

## 2. Committed persistence

- **MongoDB** for `nodes`, `edges`, `passages`, `documents`, `projects`, chat audit (minimal).
- Add v2 fields: **`introduction`** / project details (scope for prompts), staging pointers, `root_id` links, **ToDo** `status`, `node_kind`, import provenance.
- **Edges:** v1 `edges.description` often held relation **type names**; v2 stores a **single link kind** and moves human-readable rationale to optional **`note`** (importers may collapse legacy types to plain links).
- **No** requirement to migrate off Mongo for v2.

Existing projects load if schema changes are backward-compatible defaults.

---

## 3. Port list (high confidence)

| v1 path | v2 use |
|---------|--------|
| `app/tools/search_tools.py` | Fetch for inquiry + **IntraDoc** tool |
| trafilatura / arxiv / local file readers | **Any text document** normalization |
| Passage packing in `config.py` | **Intra-doc staging** only |
| Consolidation / extract prompts | Staging → `commit_intra_doc_graph` |
| `app/db.py` models | Tool adapter layer |
| `prompt_mapper.py` | Prompt ID isolation if still needed |
| `graph_analytics.py` | Optional **features** for decision model (degree, depth)—not triggers for v1 reorg |
| `graph_ingestion_engine.py` reorg / `reorg_queue.py` | **Reference only** for what *not* to run; no production port |
| `GraphCanvas.tsx`, `physicsPipeline`, `forceLayoutConfig` | **Stabilized layout** (structure key, prewarm, pinned positions, `cooldownTicks={0}`)—draw on load/topology change, not every UI tick ([02-user-experience.md](./02-user-experience.md) §5.4) |
| `graphRenderers` / node paint | Extend for v2 **color legend** (gist ROOT, deep ROOT, ToDo, etc.) |

---

## 4. Replace / wrap

| v1 path | v2 approach |
|---------|-------------|
| `app/agents/orchestrator.py` | LangGraph supervisor + composable tools |
| `app/agents/graph_navigator.py` `subgraph_expansion` | **RetrievalWorker** + gateway **reranker** query/frontier relevance (full prob vector, agent top‑k) + `highlight_nodes` |
| Auto `reorganize_overclustered_nodes` / `SPLIT_CONCEPT` | **Do not execute v1 engine.** **ReorgRecommendWorker** (DecisionScorer) + user-approved `apply_reorg_plan` |
| `POST /api/chat` + scrollback SSE | LiveKit + recommendations dock; REST `thread_id` |
| Browser Whisper → text box | Whisper-tiny in agent worker |
| Single ingest pipeline | **Gist / IntraDoc / Link / Reorg** tools |

---

## 5. Markdown import (robotics + other projects)

**Goal:** Seed Mongo graph + **decision bootstrap** from three-tier notes.

| File (cortex-os exemplar) | Import action |
|---------------------------|---------------|
| [`docs/deeper_read_notes.md`](../../docs/deeper_read_notes.md) | Create **`ROOT` + gist** per entry |
| [`docs/select_papers.md`](../../docs/select_papers.md) | Optional intra-doc concepts per deep-read source |
| [`docs/overall_insights.md`](../../docs/overall_insights.md) | Section/synthesis nodes; **`ROOT` cite edges** |

Parallel export: **`decision_training/<project>/*.jsonl`** per [05-models-and-runtime.md](./05-models-and-runtime.md).

Parser design (parenthetical paper names → arXiv ids): [10-open-questions.md](./10-open-questions.md).

Other PIs: same three-file pattern or custom importers per project.

---

## 6. Deepen existing gist ROOT (migration note)

Import and live use share one rule:

- Gist **`ROOT`** may exist without children.
- **IntraDoc** tools attach staging to **`root_id`**—no duplicate ROOT for same URI.

---

## 7. Repo layout (proposed)

```
me-mex/
  docs/             # v2 canon (this folder)
  backend/          # v2 remake in place (tag v1 for reference)
  frontend/
  voice_worker/     # always-on LiveKit voice process (separate from FastAPI)
```

**No** `backend_v2/` split—replace v1 code in `me-mex` as v2 ships ([10 A3](./10-open-questions.md#6-resolved-decisions-locked)).

---

## 8. Runtime (`main` branch)

- **Single** FastAPI app: LangGraph harness + deterministic tools under `backend/app/`.
- **No** v1 `/api/chat`, orchestrator, or feature flags—use tag **`v1`** to run the old stack.

# Graph and memory model

> **Canon:** [00-vision-and-principles.md](./00-vision-and-principles.md) §5. This document is the **data-model and tier contract** for MongoDB-backed graphs per project.

Me-Mex v2 maps your markdown research ladder onto a **per-project canvas graph**: **`ROOT`** nodes (gist or deep-read), **immutable concepts** under deep-read roots, and **mutable** nodes you author (**`CONCEPT_M`**, **insight**, **note**, **ToDo**). **Passages** and similar blobs live in Mongo for the agent—they **never** appear as graph vertices. When you cite a source in an insight you link **`ROOT`**, not `CONCEPT_I` leaves, by default.

---

## 1. Summary

- **Persistence:** **MongoDB** — evolve v1 collections (`nodes`, `edges`, `passages`, `documents`, `projects`); add metadata for status, staging, and user-authored fields.
- **Sources:** Any normalizable **text document** (arXiv PDF, blog, HTML via trafilatura, local files)—not papers-only.
- **Workflow tiers** (markdown habit): catalog → optional deep read → cross-paper notes; **canvas** node kinds are fixed in [§5](#5-canvas-node-kinds).
- **Catalog vs deep read:** Almost all sources stay **gist-only**; **every** catalogued source is still **intended for insights** once you link it. **Deep read** is the selective extra step—not “in insights or not.”
- **Operations are separate:** Gist, intra-doc graph, link/place, reorg—no bundled ingest pipeline.

---

## 2. Three tiers (markdown → graph)

| Tier | Markdown (robotics exemplar) | Graph shape |
|------|------------------------------|-------------|
| **Catalog** | `deeper_read_notes.md` | One **`ROOT`** per source; **gist** (2–3 lines) on the root |
| **Deep read** | `select_papers.md` | **Intra-document subgraph** under that `ROOT`: immutable concepts + `passage_ids` |
| **Cross-paper insights** (workflow habit) | `overall_insights.md` | Same **mutable** node kinds as the rest of the graph—hubs (`CONCEPT_M`), **insight** nodes you ask to save, links; paper cites → **`ROOT` only** (not a separate “insights document” type) |

### 2.1 Catalog vs deep read (important)

- **Volume:** Most `ROOT`s are **gist-only**.
- **Linking sources to your takeaways:** Each catalogued source can be linked to hubs or **insight** nodes via ordinary edges **you** create—there is no permanent “catalog-only, never linked” class.
- **Selectivity:** What you **skip** is usually **deep read**, not insights participation.
- **Automation:** Nothing auto-links; placement is always explicit or approved.

### 2.2 Gist on ROOT

| Path | Behavior |
|------|----------|
| **You provide gist** | Speak/type; gist tool writes `ROOT` (+ optional `source_uri`) |
| **Agent-assisted gist** | Fetch + LLM summary in panel first; gist tool commits to `ROOT` when you ask |

Inquiry and summarization **may use LangChain/LLM** without creating graph nodes.

---

## 3. Linking rule: insights → document ROOT only

Cross-paper structure **never** auto-wires through intra-document concept nodes.

| `ROOT` state | Children under `ROOT` | Insights edges |
|--------------|----------------------|------------------|
| Gist only | Gist text | **`ROOT` ↔ section/insight** when you choose |
| Deep read done | Immutable **`CONCEPT_I`** under ROOT (passages in DB, not on canvas) | **Same:** paper-level links target **`ROOT` only**, not `CONCEPT_I` leaves—unless you explicitly add other edges later |

**Deep read ≠ global merge.** Building the intra-doc graph does **not** auto-place the source in the insights tree, auto-parent under Genesis, or attach synthesis to extracted concepts.

This matches `overall_insights.md` parentheticals `(ERA)`—the **source**, not a `select_papers` subsection.

---

## 4. Canvas vs database

**On the canvas:** only the node kinds in [§5](#5-canvas-node-kinds) and **one link kind** ([§6](#6-edges)). No passages, documents, or dock text as vertices.

**Off the canvas** (Mongo / side collections, agent tools only):

| Store | Role |
|-------|------|
| **`passages`** | Chunk text backing `CONCEPT_I` or fetch for a **`ROOT`**; read via `open_passages`, staging, deep-read commit |
| **`documents`** | Normalized source payload + URI metadata (typically referenced from **`ROOT`**, not visualized) |
| **Dock transcript** | Session UX; not graph nodes |

Workflow tiers (catalog / deep read / `overall_insights` **habit**) explain **how you work in markdown**; they do **not** add extra node species beyond [§5](#5-canvas-node-kinds).

---

## 5. Canvas node kinds

**Closed list** for the unified per-project graph ([02-user-experience.md](./02-user-experience.md)); kinds are distinguished by **`metadata.node_kind` + color/label**, not separate views or document types.

| Kind | Mutability | Purpose | Canvas role |
|------|------------|---------|-------------|
| `ROOT` (gist only) | ROOT record; gist via tool | Catalog source, no `CONCEPT_I` yet | **Gist-only ROOT color** |
| `ROOT` (deep read) | Same; children added once | Source with intra-doc graph | **ROOT-with-concepts color** (gist still on ROOT) |
| `CONCEPT_I` | Immutable | Extracted claim under a ROOT | **Evidence color** (per leaf, linked to parent ROOT) |
| `CONCEPT_M` | Mutable | Hubs / structure **you** edit (Genesis spine = a `CONCEPT_M` anchor, not a new species) | **Mutable knowledge color** |
| `INSIGHT` | Mutable | Any takeaway you **explicitly** ask to keep (“save this insight”, gist-tool equivalent for ideas) | **Insight color** — **not** a special document or tier |
| `NOTE` | Mutable | Short capture from chat/voice | **Note color** — same CRUD/edit path as **`INSIGHT`** |
| `TODO` | Mutable | Action item you’ll return to (`status`: open/done) | **ToDo color**; **promote → `CONCEPT_M`** when you pick it up |

**No separate axiom node** and **no `domain_mode`.** All projects share the same node kinds and Mongo shape; **project introduction / Genesis scope** (from **P1** onboarding conversation, persisted via `update_project_scope`) steers agent prompts—not a schema switch or extra request field.

- **`CONCEPT_I`** — only **document-extracted** claims under a **`ROOT`** after deep read.
- **`CONCEPT_M`**, **`INSIGHT`**, **`NOTE`**, **`TODO`** — all **user-authored mutable** nodes; **`INSIGHT`** is a **label**, not a different persistence model or pipeline from **`NOTE`**.

v2 may map kinds to v1 `CONCEPT` + `metadata.node_kind` + `has_intra_doc_children` on ROOT.

**Derived flag:** `ROOT.deep_read = (count(CONCEPT_I under ROOT) > 0)` drives gist-only vs deep-read **color** without duplicate nodes.

---

## 6. Edges

v2 uses **one edge kind** for the whole graph—**no** v1 qualitative relation types (`SUBSET_OF`, `RELEVANT_TO`, `BUILDS_UPON`, `CONTRASTS_WITH`, `SUPERSEDES`, etc.) and **no** parallel hierarchies encoded as different edge labels.

| Rule | Meaning |
|------|---------|
| **Uniform links** | An edge is an undirected **association** between two nodes for layout, retrieval, and placement. Direction in storage (if any) is an implementation detail for tree layout—not a second class of “semantic” edge. |
| **Hierarchy = topology** | Hub under Genesis `CONCEPT_M`, `CONCEPT_I` under `ROOT`, insight linked to hub—all **the same link type**; structure comes from **which nodes you connect**. |
| **Paper cites** | Link **`ROOT` ↔ `INSIGHT`** (or hub) with **ordinary links**—same weight/kind as note ↔ `ROOT`. |
| **Equal weight** | Retrieval and layout do **not** treat some links as “more semantic”; optional filters by **node kind** only. |
| **Optional note** | Free-text **`note`** on an edge (voice/UI) when you want to remember *why* you linked—never a separate edge taxonomy. |

Decision model and retrieval treat all links **equally** unless you filter by node kind (e.g. placement candidates touching **`ROOT`** endpoints).

---

## 7. Staging (intra-document tool only)

Staging applies **only** to the **build intra-document graph** operation—not to gist-only commits or link/reorg.

1. **IntraDocWorker agent:** fetch → chunk → **LLM extract** → **`upsert_staging_bundle`** keyed by `root_id` or pending URL.
2. Agent enqueues a **recommendations dock** item (**Review / commit intra-doc graph**); you edit concept titles/descriptions there (or by voice via `edit_staging_concept`).
3. **Approve commit** on that item → immutable `CONCEPT_I` (+ passages) **under that `ROOT` only** (`commit_intra_doc_graph` + `interrupt` preview on the same item).

You can **deepen an existing gist `ROOT`** later: same staging path, same root id, no duplicate source node.

There is **no** v2 auto-commit that also links, generalizes, or reorganizes.

---

## 8. Multiple projects

Each **project** workspace in Mongo:

- Own **introduction / scope text**, Genesis description, catalog `ROOT`s, deep-read subgraphs, insights tree.
- **No** cross-project edges unless import/copy.
- Robotics acceptance fixtures: `docs/deeper_read_notes.md`, `select_papers.md`, `overall_insights.md` (cortex-os).

---

## 9. Partitions and crowded sections

**No separate partition/tag layer**—**one** graph, **uniform edges** ([§6](./03-graph-and-memory.md#6-edges)). Crowded `overall_insights`-style sections appear as **hubs** (`CONCEPT_M`) + linked **`INSIGHT`** nodes on the **same canvas**:

- **Reorg recommendations** (decision model): split labels, relocations, orphan targets—then **preview diff** and your approval.
- **Apply** via `apply_reorg_plan` / topology tools only after approve.
- **Not** v1 `reorganize_overclustered_nodes` or generative `SPLIT_CONCEPT` token cascades.

**Canvas:** single graph with **color legend** ([02-user-experience.md](./02-user-experience.md) §5.2)—not separate catalog/depth/insights view modes.

---

## 10. Nudges vs training traces

- **Dock recommendations** (reconnect after delete, placement, reorg, deep read, gist ROOT) are computed from **live graph state + session**—not a persisted “workflows graph” collection.
- **Decision-model training** uses **`decision_traces`** / bootstrap JSONL only ([05 §8](./05-models-and-runtime.md#8-decision-trace-schema-training--eval))—including labels derived from notes joins and live accept/correct.
- Nudges **initiate** guided flows; they **never** auto-execute graph writes ([06 §0](./06-workflows.md#0-how-recommendations-work-all-workflows)).

---

## 11. Markdown habit → graph (corrected)

| Habit | Graph equivalent |
|-------|------------------|
| `deeper_read_notes` entry | `ROOT` + gist |
| `select_papers` bullets | Intra-doc concepts under that `ROOT` |
| `overall_insights` section heading | `CONCEPT_M` hub under Genesis anchor |
| Numbered bullet + `(Paper)` cites | **`INSIGHT`** node you commit manually; **link** to cited **`ROOT`** (same edge kind as all other links) |
| Subgroup when section crowded | **ReorgRecommendWorker** → `preview_reorg_diff` → `apply_reorg_plan` |
| Idea while reading | `NOTE` / **ToDo**; optional link to `ROOT` or section |
| ToDo you revisit | **ToDo** → **`promote_todo_to_concept_m`** (or voice equivalent) |

**Not:** linking insights directly to `CONCEPT_I` by default, or auto-ingest on URL paste.
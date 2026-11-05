# Master Architecture & Technical Specification: Me-Mex

> **Document Purpose**: Single master technical specification for **Me-Mex** (v0.2): system architecture, 3-element graph topology, mutability hierarchy, **Genesis-rooted tree traversal**, graph navigator workflows, engine-dispatch reorganization, WebGL UI/UX, REST/SSE API, FastMCP tools, and backend test specifications.

---

## 1. System Motivation & Macro Scope

Me-Mex is an **Agentic External Memory System** designed to function as an external extension of your brain for organizing, synthesizing, and retrieving textual knowledge—including academic research papers, technical blogs, and YouTube video transcripts—without manual note scrolling or cognitive overload.

### Core Problems Addressed
1. **Manual Overhead & Linear Scrolling**: Reviewing massive paper additions daily via linear text file scrolling is inefficient.
2. **Context Fragmentation**: Manually linking new papers to past literature or updating concept clusters requires high cognitive load.
3. **Implicit Relationships**: Complex cross-paper dynamics (supersedes, contrasts, co-occurs) are implicit rather than visually navigable.
4. **Cascade Depth Trap (v0.2 fix)**: Prior wrapper-only splits under every overflowing hub pushed subtrees deeper on each reorg; v0.2 uses **lateral sibling splits** everywhere except Genesis.

---

## 2. Core Architecture & System Lifecycle

Me-Mex operates on a continuous **Conversational Gateway (`POST /api/chat`)** loop. **Conversation** streams immediately; **Retrieval** and **Ingestion** run graph phases first, then a final **Conversation** response.

```
       ┌──────────────────────────────────────────────────────────┐
       │         [User Message / Input pasted into Chat]           │
       └────────────────────────────┬─────────────────────────────┘
                                    │
                                    ▼
       [PHASE 0: UNIFIED CONVERSATIONAL GATEWAY (POST /api/chat)]
       - Executive Orchestrator analyzes query & chat history
       - Routes to ONE of three paths:
           1. CONVERSATION (direct LLM stream)
           2. RETRIEVAL    (Genesis tree traversal → conversation)
           3. INGESTION    (Phase 1 intra-doc → Phase 2 tree traversal → Phase 3 linking
                            → Phase 3.5 generalization → Phase 4 reorg → conversation)
                                    │
           ┌────────────────────────┼────────────────────────┐
           │                        │                        │
           ▼                        ▼                        ▼
     [CONVERSATION]            [RETRIEVAL]              [INGESTION]
           │                        │                        │
           └────────────────────────┴────────────────────────┘
                                    │
                                    ▼
                 [FINAL CONVERSATION RESPONSE STREAM]
```

### Operational Path Breakdown

1. **Path 1: `CONVERSATION`** — Direct LLM response without graph traversal.
2. **Path 2: `RETRIEVAL`**
   - **Step 1**: Single **`GraphNavigator`** walks the **mutable tree from Genesis** (`traverse_mutable_tree_from_genesis`), presenting mutable children and read-only immutable neighbors each hop (immutable nodes are context only; frontier expansion is mutable-only).
   - **Step 2**: Final conversation synthesizes retrieved graph context.
3. **Path 3: `INGESTION`**
   - **Phase 1**: Document fetch, scale-adaptive chunking (1–30 passages), LLM concept extraction and consolidation (same tiering as v0.1).
   - **Phase 2**: Genesis-rooted tree traversal (same navigator as retrieval).
   - **Phase 3**: Collective linking — each immutable → **highest suitable mutable anchor** on a Genesis path (not forced deepest frontier); paths supplied in prompt payload.
   - **Phase 3.5**: Target generalization on mutable nodes that received new edges this pass.
   - **Phase 4**: Single call **`GraphNavigator.reorganize_overclustered_nodes`** (discover, execute, cascade). Seeds = link-affected mutables only. **`ReorgQueue`**: discover splits FIFO; parent cascade **FILO** after orphan promotion; **sibling deferral** (parent split waits until discover siblings under same tree parent finish). Cap: **`MAX_UPWARD_REORG_ITERATIONS`**. Engine: wrapper/replacement + rewire closure + **`SUBSET_OF`** on tree reparent.

---

## 3. Clean 3-Element Topology & Universal Storage Schema

### Graph Topology

- **Periphery**: `ROOT` nodes and **immutable** intra-document concepts (evidence).
- **Core**: **Mutable** domain hubs and intermediates on a **`SUBSET_OF` tree backbone** rooted at Genesis (`concept_genesis` / title **Everything**).
- **Typed edges**: Semantic relations (`RELEVANT_TO`, `SUPERSEDES`, etc.) plus **`SUBSET_OF`** for hierarchy.

```mermaid
graph TD
    subgraph Active Graph Network Topology (No Passages)
        Paper[Root Node: Paper (Immutable)] -->|RELEVANT_TO| ConceptPixel[Intra-Doc Concept (Immutable)]
        ConceptPixel -->|RELEVANT_TO| HubA[Mutable Hub A]
        HubA -->|SUBSET_OF| Genesis[Genesis: Everything (Mutable)]
        HubB[Mutable Hub B] -->|SUBSET_OF| Genesis
    end

    subgraph Out-of-Graph Storage
        Passage1[Passage Chunk]
    end

    ConceptPixel -.->|passage_ids| Passage1
```

### Node & Edge Schema Taxonomy

1. **`ROOT` (immutable)** — One per ingested document; not a reorg target.
2. **`CONCEPT`**
   - **Immutable intra-doc** (`metadata.immutable: true`) — Extracted evidence; agents may **link to** them, not edit/split/delete.
   - **Mutable hubs** (`immutable: false`) — Created during ingestion; `EDIT_CONCEPT`, `SPLIT_CONCEPT`, generalization allowed.
3. **Genesis** — `metadata.is_genesis`; title locked to **Everything**; **single user/LLM-editable `description`** (project scope).
4. **Edges (`GraphEdge`)**
   - Qualitative `description` (relation type, e.g. `RELEVANT_TO`, `SUBSET_OF`). No semantic attachment bucket metadata.

Optional **computed** mutable-node metadata (refreshed after link/reorg): `tree_depth_from_genesis`, `subtree_mut_height`, `strahler_order`, `subtree_immutable_count`.

### Hierarchy of Mutability

| Layer | Mutability | Reorg commit shape |
|-------|------------|-------------------|
| Genesis (`Everything`) | Mutable; title fixed | **Wrapper** — mint department hubs under Genesis only for sub-concepts that receive ≥1 neighbor in rewire; ungrouped neighbors stay on Everything (`EVERYTHING` alias) |
| Other mutable hubs | Mutable | **Replacement** — hub becomes first sibling; additional sub-concepts minted under `Parent(H)`; ungroupable neighbors rewire to `Parent(H)` |
| Intra-doc concepts | Immutable | N/A |
| Root nodes | Immutable | N/A |

**Hub discovery (removed in v0.2):** No eigenvector centrality, Voronoi partitions, or multi-persona routing. Construction is **lateral** except at Genesis; search is **top-down from Genesis**.

---

## 4. Graph Navigator Workflow (v0.2)

**Module:** `app/agents/graph_navigator.py` — one navigator per ingestion/retrieval, anchored on project Genesis.

**Prompts:** `graph_tree_traversal.md`, `graph_link_intradoc.md`, `graph_reorg_discover.md`, `graph_reorg_partition.md`, plus orchestrator prompts (`collective_ingestion_linking`, `target_node_generalization`, etc.).

### 4.1 Tree traversal

1. Start at `get_genesis_node(project_id)`; inject Genesis **description** as scope.
2. Each hop: LLM selects mutable **tree children** (metadata-backed backbone); immutables shown but not expandable.
3. Depth capped by `MAX_TRAVERSAL_DEPTH` (default 3–4); depth penalty in prompt.
4. Returns `explored_nodes`, `traversed_node_ids`, and `node_touched` entries in `emitted_events` (orchestrator persists to the event queue when streaming).

### 4.2 Linking

- Phase 3 orchestrator prompt **`collective_ingestion_linking`** (with **`mutable anchor paths`**: Genesis → each traversal frontier).
- Rule: **highest suitable anchor** — shallowest mutable on a path that is semantically better than any descendant on that path; Genesis fallback only if no path node qualifies.
- `link_intradoc_concepts` remains available for alternate call sites; ingestion uses collective linking + Phase 3.5 generalization.

### 4.3 Reorganization (v0.2.3 — unified Phase 4 in navigator)

**Entry point:** `GraphNavigator.reorganize_overclustered_nodes` with `plan_only=False` (orchestrator passes `doc_title`, `proj_list`). Tests use `plan_only=True` for command payloads only.

**Discovery (once):** Link-affected mutable targets → `effective_degree ≥ τ` → LLM **`graph_reorg_discover`** → build split commands for selected hubs.

**Work queue** (`app/services/reorg_queue.py`):

1. After LLM discover, enqueue **hub IDs only** at **tail** (FIFO).
2. Pop front → **`build_split_command_for_hub(hub_id)`** (same for discover and cascade) → **`execute_single_command`** → refresh metadata.
3. If tree parent is hot **and** discover **siblings** under that parent are drained → **prepend parent hub ID** (FILO); split built on that hub’s pop.
4. Repeat until queue empty; cascade prepends capped by **`MAX_UPWARD_REORG_ITERATIONS`** per Phase 4 pass. `plan_only` runs the pop/build loop without execute or cascade enqueue.

**Partition (per hub):** One LLM call — **`graph_reorg_partition`** (`ReorgPartitionPayload`, `REORG_PARTITION_MAX_TOKENS` default 6144). Three lists:

1. **`sub_concepts`** — at least one sub; each sub must have **≥ 2** neighbors in `rewired_edges` (LLM contract).
2. **`overflow_neighbors`** — neighbors promoted to **Everything** (Genesis) or **ancestor** (replacement); not listed in `rewired_edges`.
3. **`rewired_edges`** — **sub assignments only** (`sub_*` aliases).

Upstream **`effective_degree ≥ τ`** gates neighbor count before partition. Post-parse: **`validate_reorg_partition`** (retry on failure, no programmatic demotion) → **`merge_partition_to_engine_rewires`** → **`finalize_rewire_edges`**.

**Commit:** wrapper at Genesis (lazy mint — only aliases with assigned neighbors), replacement elsewhere (`graph_ingestion_engine.py`). Replacement splits **sever** the split target’s link to its tree parent, then attach each sub via uniform edges and `mutable_parent_id` metadata. Graph edges are **unweighted and undifferentiated** (optional NL `description` only). Partition neighbor batches **exclude** mutable tree children when splitting a parent hub. Each committed neighbor edge emits **`reorg_neighbor_rewired`** before **`reorg_completed`**.

Cardinality: **1 ≤** sub count **≤ ⌊n/2⌋**. **`graph_health_metrics`** emitted once after the queue drains.

**Out of v0.2 scope:** `COLLAPSE_CONCEPT` (UI delete uses existing delete-node API); optional PPR/shortcut edges deferred.

### 4.4 Integer indexing prompt protocol

- Dual `PromptIdMapper` caches: `passage_mapper`, `concept_mapper`.
- LLM sees integer indices only; orchestrator/navigator map back to MongoDB IDs before persistence.

---

## 5. WebGL UI/UX Specification & Visual Palette Mapping

(Unchanged from v0.1 except where noted.)

- **Genesis / mutable description edit:** `PATCH /api/nodes/{node_id}` updates `description`; Genesis **title** remains **Everything**.
- **Right drawer:** Editable description for mutable nodes and Genesis.
- **Canvas search:** Indexes `title`, `id`, `description`.
- **SSE visualization:** Frontend may still listen for legacy event names (`persona_traversal_*`) while also handling `graph_traversal_*`; `node_touched` carries `persona_id`/`persona_name` fields mapped from navigator scope for backward-compatible UI glows.

### Speech-to-Text (STT)

In-browser Whisper (`@xenova/transformers`); editable draft in chat input before send.

---

## 6. API Endpoint Specification & FastMCP Tools

### REST API Routes

- `POST /api/chat` — Unified gateway (conversation, retrieval, ingestion).
- `GET /api/graph?project_id=...` — Project-scoped topology.
- `PATCH /api/nodes/{node_id}` — Update node description (Genesis title locked).
- `GET/POST /api/projects`, project chat history, passages, etc.

### Telemetry Stream (`GET /api/sse/chat`)

Examples: `intent_classified`, `node_touched`, `graph_traversal_start`, `graph_traversal_active`, `graph_health_metrics`, `reorg_completed`, `chat_complete`.

### FastMCP Tools

- `search_duckduckgo_web`, `search_arxiv_papers`, `fetch_web_article`, `get_graph_nodes`, `get_passages_by_ids`, `get_macro_documents`
- **`calculate_hub_rankings`** — **Repurposed (v0.2):** returns **mutable tree health metrics** from `MutableTreeIndex.refresh_tree_metadata`, not eigenvector hub rankings.

### Configuration (v0.2)

| Setting | Default | Role |
|---------|---------|------|
| `DEGREE_THRESHOLD` | 7 | Reorg trigger |
| `MIN_CLUSTER_SIZE` | 2–3 | Genesis department minting |
| `MAX_TRAVERSAL_DEPTH` | 3–4 | Tree walk cap |
| `REACHABILITY_HOP_K` | K for immutable reachability metric |

---

## 7. Backend Test Specification & Verification

### Test database

Isolated `test-me-mex` (`DB_NAME="test-me-mex"`).

### Execution

```bash
cd me-mex/backend
python -m pytest tests
```

Use at most **2** parallel workers (`pytest -n 2`).

### v0.2 test focus

- **`test_graph_analytics.py`** — `MutableTreeIndex`, tree metadata refresh (no Voronoi/hub centrality).
- **`test_graph_navigator.py`** — Traversal, immutable frontier blocking, reorg telemetry, tree candidate filtering.
- **`test_reorg_simulation.py`** — Wrapper (Genesis) vs lateral commit behavior.
- **`test_concept_reconciliation.py`** — Immutability enforcement, `execute_single_command` / split dispatch.

---

## 8. Analytics Module (`graph_analytics.py`)

- **`MutableTreeIndex`**: Parent/child via `SUBSET_OF`, depth from Genesis, subtree height, Strahler order, Sackin index, K-hop immutable reachability.
- **`build_rustworkx_graph`**: Retained for general graph ops where needed.
- **Removed:** `get_top_concept_hubs`, Voronoi `partition_department_communities`, eigenvector hub pipeline.

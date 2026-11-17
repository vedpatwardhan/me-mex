# Models and runtime

> **Canon:** [00-vision-and-principles.md](./00-vision-and-principles.md) §8. **Decision usage:** [04-agent-orchestration.md](./04-agent-orchestration.md).

v2 runs **Ministral 3 8B** + **LoRA decision** on Colab **vLLM** (remote inference only). **LangGraph agents**, LiveKit worker, MongoDB, and **checkpoint JSON** run **locally** on your machine; workers call Colab over HTTP. **Whisper-tiny** + **Kokoro** for voice (local or Colab per [10 M1](./10-open-questions.md#6-resolved-decisions-locked)). LoRA is trained from **legacy markdown notes** + live traces—**no** logprob-only decision MVP.

---

## 1. Committed platform stack

| Layer | Choice | v2 starting point |
|-------|--------|-------------------|
| Graph DB | **MongoDB** | — |
| Chat / agents LLM | `mistralai/Ministral-3-8B-Instruct-2512` via **vLLM** (`/v1`) | Required before interactive agents |
| **Decision routing** | **LoRA adapter** on Ministral 3 8B (`--enable-lora`); option-ranking head | **Train from notes bootstrap**, deploy with stack—same tier as STT/TTS |
| STT | **Whisper-tiny** (or tiny.en) | Wired in Phase 2 voice |
| TTS | **Kokoro** (~82M) | Wired in Phase 2 voice |
| VAD | Silero or LiveKit | — |
| Voice + agent | **LiveKit** + LangGraph | — |

Config: FP8 / `--enable-auto-tool-choice` / `--tool-call-parser mistral` as in v1 Colab setup.

**Not shipped:** `max_tokens=1` logprob scoring over labeled options as the production decision path ([09-phasing.md](./09-phasing.md)).

---

## 2. Chat / tool-calling LLM

**Used for:** Supervisor and worker **agents**—inquiry replies, gist assistance, **intra-doc extract/consolidate loops**, spoken responses.

**Not used for:** Inside **deterministic tools** (Mongo, staging I/O, dock queue).

**Not used for:** Per-hop generative BFS (replaced by **LoRA decision adapter** in **RetrievalWorker**).

Heavy extract/consolidation runs only when **IntraDocWorker** is routed—not on every summary.

**Project scope:** When `projects.introduction` (and synced Genesis description) is set, **ContextPreprocessor** prepends it to supervisor and worker system prompts—see [04-agent-orchestration.md](./04-agent-orchestration.md) §7. No `domain_mode` or alternate model profiles.

---

## 3. Decision model — LoRA from bootstrap notes

### 3.1 Purpose — relevance over a candidate batch (replaces v1 `subgraph_expansion`)

v1 **`GraphNavigator.subgraph_expansion`**: each BFS hop called the chat LLM to **generate text** picking the next node—slow ([01-v1-baseline.md](./01-v1-baseline.md)).

v2 **DecisionScorer**: same traversal shape, **no generative hop**. At each step:

1. Hold the **query node** — the **concept you are checking** (retrieval seed, selected canvas node, `ROOT` you are placing, mutable node in reorg, etc.).
2. Gather the **frontier** — all nodes to compare in **this** step (BFS neighbors, hub shortlist, relocation options, …).
3. Model returns **relevance probabilities (or scores) for every frontier node** w.r.t. the query node—**full vector over the input list**, not top‑k inside the model.
4. The **agent** sorts, takes **top‑k** (or threshold), **expands** those next—bounded BFS / highlight, same as today’s hop loop but sub‑250 ms per batch.

One LoRA head everywhere: only **who is query** and **who is on the frontier** change between retrieval, placement, and reorg.

Low max relevance → escalate: more neighbors in the batch, `open_passages`, or ask you.

**Invocation:** **DecisionScorer** runs **inside worker agents** ([04 §5](./04-agent-orchestration.md#5-agents-vs-tools))—never inside tools.

### 3.2 Delivery order (v2 — no logprob MVP)

Same philosophy as **Whisper-tiny / Kokoro**: pick the model up front, wire it in the stack; do **not** ship placement/highlight/reorg suggest on an untrained logprob hack.

| Step | What | Notes |
|------|------|-------|
| **1 — Bootstrap JSONL** | Parse per-project markdown (`deeper_read_notes`, `select_papers`, `overall_insights`) into **labeled decision traces** | Robotics exemplar first ([§3.3](#33-bootstrap-signal-per-project)) |
| **2 — LoRA train** | Fine-tune adapter: **query node + frontier → relevance prob per frontier node** | Held-out **before** interactive retrieval/placement ships |
| **3 — Deploy** | Mount adapter on Colab vLLM; **DecisionScorer** | **LinkPlace**, **Retrieval**, **ReorgRecommend** agents (same API) |
| **4 — Live collection** | Append accepts/corrections to `decision_traces/` | Retrain or refresh adapter on a cadence (post–v2 ops) |

Feasibility research assumed live-only trajectories; **your notes already encode routing labels**—so **LoRA is the entry point**, not a later swap-in.

### 3.3 Bootstrap signal (per project)

**Goal:** Build LoRA training JSONL by **joining the three markdown tiers**—not by parsing parentheticals in isolation.

| Source file | Role in dataset |
|-------------|-----------------|
| `deeper_read_notes.md` | **ROOT** identity, title, **gist** text per source |
| `select_papers.md` | Intra-doc concept groupings under sources (placement context) |
| `overall_insights.md` | Section hubs, numbered insights, **which sources** each insight cites, subgroup / crowded-section structure |

Pipeline:

1. **Align** sources across files (titles, arXiv ids, parenthetical cites → `deeper_read_notes` rows).
2. Reconstruct synthetic graph (sections = `CONCEPT_M`, sources = `ROOT`s, insights = nodes, cites = edges).
3. Emit JSONL **decision traces**: **query_node** + **frontier[]** + **`label_relevance`** (full vector)—placement, retrieval hops, reorg moves implied by the notes graph.
4. Hold out for **eval** on **full frontier** vectors ([00 §9](./00-vision-and-principles.md)).

Import tooling: [08-migration-and-reuse.md](./08-migration-and-reuse.md).

### 3.4 Inference (DecisionScorer)

- **Input:**
  - **`query_node`** — concept under test `{ id, title, node_kind, gist?, … }`
  - **`frontier[]`** — **all** nodes to score this step (BFS neighbors, placement shortlist, etc.)
  - Optional **project scope** snippet (not a mode enum)
- **Model:** LoRA-tuned Ministral 3 8B via vLLM (same host as chat; dedicated adapter id)
- **Output:** `relevance_probs` — **one entry per frontier `id`** (normalized over the batch). **Must cover 100% of input frontier ids**; never return only top‑k. Agent applies top‑k / threshold **after** inference for expand/highlight/dock.
- **Tests:** Headless pytest may **mock** DecisionScorer; integration / voice paths use **real LoRA** once Phase 1 decision exit is met ([09-phasing.md](./09-phasing.md))

### 3.5 Adapter scope

One global vs per-project LoRA: [10-open-questions.md](./10-open-questions.md) M2.

---

## 4. Embeddings

Reuse v1-style local embedder **from agents** (not inside tools):

- Precompute query vectors before `query_nodes_by_embedding`
- Building **frontier batches** for DecisionScorer training/inference (optional pre-filter before full relevance pass)
- Dormant-note / recommendation cosine match

---

## 5. Speech pipeline

```
LiveKit room
  → VAD
  → Whisper-tiny (STT)
  → LangGraph turn (text + context_json)
  → Kokoro (TTS)
```

Barge-in cancels **foreground** stream mid-utterance.

**Hosting:** Prefer **single Colab GPU** (e.g. L4) for vLLM + LoRA + STT/TTS when memory allows; else STT/TTS **locally** on Mac—avoid multiple GPU VMs ([10 M1](./10-open-questions.md#6-resolved-decisions-locked)).

---

## 6. Runtime topology (local agents + Colab models)

**Split:** Colab hosts **models only**; your Mac runs **agents and product stack**.

```
[Local — your machine]
  ├── React UI + LiveKit client
  ├── FastAPI (graph CRUD, REST agent turns)
  ├── MongoDB (knowledge graph)
  ├── backend/data/checkpoints/   # LangGraph JSON per thread_id
  ├── Always-on LiveKit + LangGraph agent worker (calls remote vLLM)
  ├── Whisper-tiny + Kokoro (default local; optional on Colab if needed)
  └── HTTPS or SSH tunnel → Colab OpenAI-compatible /v1

[Colab — prefer one L4]
  └── vLLM: Ministral 3 8B + **LoRA decision adapter** (--enable-lora)
      (no LangGraph, no Mongo, no checkpoint files on the notebook VM)
```

**Implication:** Session checkpoint durability is **local disk**—not tied to Colab VM lifetime. Colab restarts only require reconnecting the vLLM endpoint; agent `thread_id` state survives on your machine.

---

## 7. Latency targets

| Step | v1 (order of magnitude) | v2 target |
|------|-------------------------|-----------|
| Retrieval hop | multi-second LLM expand | <250 ms **LoRA** decision hop |
| Intra-doc extract | many sequential LLM calls | **IntraDocWorker agent** only; batched where possible |
| Voice TTFA | N/A (text-first) | <2 s; <1.2 s stretch |

---

## 8. Decision trace schema (training / eval)

One row shape everywhere—relevance of each frontier node w.r.t. `query_node`. No `task_type`.

```json
{
  "project_id": "robotics",
  "provenance": "live_session | bootstrap_notes | v1_subgraph_expansion_trace",
  "graph_snapshot_id": "…",
  "query_node": { "id": "…", "title": "…", "node_kind": "CONCEPT_M" },
  "frontier": [
    { "id": "…", "title": "…", "node_kind": "ROOT" },
    { "id": "…", "title": "…", "node_kind": "CONCEPT_I" }
  ],
  "label_relevance": { "…frontier_id…": 1.0, "…other…": 0.0 },
  "model_relevance_probs": { "…every frontier id…": 0.0 },
  "user_expanded_ids": ["…"],
  "timestamp": "…"
}
```

- **`query_node`** — the concept whose relevance to the frontier is being scored (BFS current node, placement `ROOT`, etc.).
- **`frontier`** — full batch passed to the model; **`model_relevance_probs`** must have **the same keys** as frontier ids.
- **`provenance`** — dataset metadata only.
- Bootstrap from notes + optional import of v1 hop traces; live rows log expands you chose vs model vector.

- Bootstrap JSONL: `backend/data/decision_training/<project>/`
- Live append: `backend/logs/decision_traces/`
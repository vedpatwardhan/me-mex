# Models and runtime

> **Canon:** [00-vision-and-principles.md](./00-vision-and-principles.md) §8. **Decision usage:** [04-agent-orchestration.md](./04-agent-orchestration.md). **Retrieval analysis:** [../reports/2026-11-18-retrieval-methods.md](../reports/2026-11-18-retrieval-methods.md).

v2 runs **four remote models** on one Colab **inference gateway**—**Ministral 3 8B** (vLLM chat/tools), **cross-encoder reranker** (decision routing), **Whisper base.en** (CPU int8 in speech sidecar), **edge-tts** (Colab Python 3.13)—behind a single HTTPS URL. **LangGraph agents**, LiveKit, MongoDB, and **checkpoint JSON** run **locally**; workers call Colab over HTTP. **No fine-tuning** is required to ship P2–P4 routing; bootstrap JSONL and live traces support **eval** and **optional** reranker fine-tune later.

**Not shipped:** generative JSON or chat-LLM hops for decision routing; LoRA-on-Ministral decision adapter; untrained logprob-only routing ([09-phasing.md](./09-phasing.md)).

---

## 1. Committed platform stack

| Layer | Choice | v2 starting point |
|-------|--------|-------------------|
| Graph DB | **MongoDB** | — |
| Chat / agents LLM | `mistralai/Ministral-3-8B-Instruct-2512` via **vLLM** (`/v1`) | Required before interactive agents |
| **Decision routing** | **Off-the-shelf cross-encoder reranker** on gateway (`POST /v1/decision/score`)—e.g. `BAAI/bge-reranker-base` | Same Colab stack as STT/TTS; **CPU**; no generative hop |
| STT | **Whisper base.en** (`faster-whisper`, CPU **int8**; optional `small` / HF distil) | Colab speech sidecar — **does not use GPU** with `WHISPER_DEVICE=cpu` |
| TTS | **edge-tts** (Colab) | Colab speech sidecar (see `colab/speech_sidecar.py`) |
| VAD | Silero or LiveKit | — |
| Voice + agent | **LiveKit** + LangGraph | — |

Config: FP8 / `--enable-auto-tool-choice` / `--tool-call-parser mistral` as in v1 Colab setup.

Gateway topology: [colab/TOPOLOGY.md](../colab/TOPOLOGY.md).

---

## 2. Chat / tool-calling LLM

**Used for:** Supervisor and worker **agents**—inquiry replies, gist assistance, **intra-doc extract/consolidate loops**, spoken responses, retrieval **summaries** after highlight.

**Not used for:** Inside **deterministic tools** (Mongo, staging I/O, dock queue).

**Not used for:** Per-hop graph routing (replaced by **cross-encoder DecisionScorer** in **RetrievalWorker**, **LinkPlaceWorker**, **ReorgRecommendWorker**).

Heavy extract/consolidation runs only when **IntraDocWorker** is routed—not on every summary.

**Project scope:** When `projects.introduction` (and synced Genesis description) is set, **ContextPreprocessor** prepends it to supervisor and worker system prompts—see [04-agent-orchestration.md](./04-agent-orchestration.md) §7. No `domain_mode` or alternate model profiles.

---

## 3. Decision routing — cross-encoder reranker

### 3.1 Purpose — relevance over a candidate batch (replaces v1 `subgraph_expansion`)

v1 **`GraphNavigator.subgraph_expansion`**: each BFS hop called the chat LLM to **generate text** picking the next node—slow ([01-v1-baseline.md](./01-v1-baseline.md)).

v2 **DecisionScorer**: same traversal shape, **no generative hop**. At each step:

1. Hold the **query node** — the concept you are checking (retrieval **current** node after seed, selected canvas node, `ROOT` you are placing, hub in reorg, etc.).
2. Gather the **frontier** — all nodes to compare in **this** step (BFS neighbors, placement shortlist, relocation options, …).
3. Reranker returns **relevance probabilities for every frontier node** w.r.t. the query—**full vector over the input list** (softmax over batched pair scores), not top‑k inside the server.
4. The **agent** sorts, takes **top‑k** (or threshold), **expands** those next—bounded BFS / highlight.

**Retrieval seed:** default **Genesis** when no `query_node_id` / selection; override via context ([06 W11](./06-workflows.md#10-w11--retrieval)).

**Pair text:** encode `title` + `description`/`gist` + `node_kind` for query and each frontier node.

Low max relevance → escalate: more neighbors, `open_passages`, or ask you.

**Invocation:** **DecisionScorer** runs **inside worker agents** ([04 §5](./04-agent-orchestration.md#5-agents-vs-tools))—never inside tools. Production: **`HttpDecisionScorer`** → gateway; CI: **mock**.

### 3.2 Delivery order (v2 — no fine-tune gate for P2–P4)

| Step | What | Notes |
|------|------|-------|
| **1 — Gateway reranker** | Load cross-encoder on Colab gateway; implement `decision/score` | Off-the-shelf weights; batched pairs |
| **2 — Bootstrap JSONL** | Notes → labeled traces for **eval** | Robotics exemplar ([§3.3](#33-bootstrap-signal-per-project)) |
| **3 — Eval baseline** | Held-out top-1 / coverage on val JSONL via gateway or same weights | Informs quality; not a train blocker |
| **4 — Live collection** | Append accepts/corrections to `decision_traces/` | Optional reranker fine-tune in P4+ |

### 3.3 Bootstrap signal (per project)

**Goal:** Build **eval and future training** JSONL by **joining markdown tiers**—not required to ship routing.

| Source file | Role in dataset |
|-------------|-----------------|
| `deeper_read_notes.md` | **ROOT** identity, title, **gist** text per source |
| `select_papers.md` | Intra-doc concept groupings under sources (placement context) |
| `overall_insights.md` | Section hubs, numbered insights, **which sources** each insight cites |

Pipeline:

1. **Align** sources across files (titles, arXiv ids, parenthetical cites → `deeper_read_notes` rows).
2. Reconstruct synthetic graph (sections = `CONCEPT_M`, sources = `ROOT`s, insights = nodes, cites = edges).
3. Emit JSONL: **query_node** + **frontier[]** + **`label_relevance`** (full vector).
4. Hold out for **eval** on **full frontier** vectors ([00 §9](./00-vision-and-principles.md)).

Import tooling: [08-migration-and-reuse.md](./08-migration-and-reuse.md).

### 3.4 Inference (DecisionScorer)

- **Input:**
  - **`query_node`** — `{ id, title, node_kind, gist?, description?, … }`
  - **`frontier[]`** — **all** nodes to score this step
- **Transport:** `POST {COLAB_INFERENCE_BASE_URL}/v1/decision/score` (same gateway host as chat; see [colab/TOPOLOGY.md](../colab/TOPOLOGY.md))
- **Server:** Cross-encoder forward on **query × each frontier** → logits → **softmax** → `relevance_probs`
- **Output:** **one entry per frontier `id`** (normalized). **Must cover 100%** of input ids. Agent applies top‑k **after** scoring.
- **Config (local):** `DECISION_SCORER_MODE=live|mock`; default HF id set on **gateway** env (e.g. `BGE_RERANKER_MODEL`)
- **Tests:** pytest uses **mock**; integration uses **live** gateway (`pytest -m vllm`) for chat + decision ([09-phasing.md](./09-phasing.md), [11-testing.md](./11-testing.md))

### 3.5 Future: fine-tuned reranker

Optional per-project or global reranker checkpoint on the same endpoint: [10-open-questions.md](./10-open-questions.md) M2. Alternatives (ColBERT, decision heads) are out of initial scope—see [retrieval-methods report](../reports/2026-11-18-retrieval-methods.md).

---

## 4. Embeddings (deferred)

**Not on the critical path** for placement or BFS when the frontier is **graph neighbors** and retrieval seeds from **Genesis** or selection.

Optional later **from agents** (not inside tools):

- `query_nodes_by_embedding` when global recall over the corpus is needed
- Dormant-note / recommendation cosine match

Until then, `query_nodes_by_embedding` may remain a stub; keyword search remains available.

---

## 5. Speech pipeline

```
LiveKit room (browser mic)
  → Silero VAD (local agent worker, CPU)
  → Whisper base.en (STT, Colab speech sidecar, CPU int8)
  → LangGraph turn (text + context_json, local backend)
  → edge-tts (TTS, Colab)
```

Utterances end on Silero **end-of-speech** (~550 ms trailing silence by default) or **flush on mute** (push-to-talk). Tunables: `VOICE_VAD`, `VOICE_MIN_SILENCE_MS`, `VOICE_MIN_UTTERANCE_MS` on the worker — see [agent/.env.example](../agent/.env.example).

Barge-in cancels **foreground** stream mid-utterance.

**Hosting:** **Single Colab VM**—vLLM on GPU; **Whisper + Kokoro + reranker on CPU** via gateway/sidecar ([10 M1](./10-open-questions.md#6-resolved-decisions-locked)). Local LiveKit + agents unchanged.

---

## 6. Runtime topology (local agents + Colab model server)

**Split:** Colab hosts **all model weights** behind **one gateway URL**; your Mac runs **agents and product stack**.

```
[Local — your machine]
  ├── React UI + LiveKit client
  ├── FastAPI (graph CRUD, REST agent turns)
  ├── MongoDB (knowledge graph)
  ├── backend/data/checkpoints/   # LangGraph JSON per thread_id
  ├── LiveKit + LangGraph agent worker (HTTP → Colab gateway)
  └── Mock DecisionScorer in CI; live HTTP to gateway in dev/prod

[Colab — one L4 VM]
  inference_gateway :7860  (public via cloudflared)
    ├── proxy /v1/*  →  vLLM :8000  (Ministral 3 8B, GPU)
    ├── POST /v1/decision/score  →  cross-encoder reranker (CPU)
    └── proxy STT/TTS  →  speech_sidecar :7861 (Whisper + edge-tts, CPU)
```

vLLM runs in a **separate process** on the GPU; CPU models do not compete for 8B VRAM.

**Implication:** Checkpoints and graph state are **local**. Colab restarts only require a new tunnel URL; reconnect `COLAB_INFERENCE_BASE_URL`.

---

## 7. Latency targets

| Step | v1 (order of magnitude) | v2 target |
|------|-------------------------|-----------|
| Retrieval hop | multi-second LLM expand | **RTT + rerank batch**; aim p95 **&lt;250 ms per hop** (multi-hop = multiple HTTP calls) |
| Intra-doc extract | many sequential LLM calls | **IntraDocWorker** only; batched where possible |
| Voice TTFA | N/A (text-first) | &lt;2 s; &lt;1.2 s stretch |

See [07-performance-and-observability.md](./07-performance-and-observability.md).

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

- **`model_relevance_probs`** — scorer output at log time; keys must match **frontier** ids.
- Bootstrap JSONL: `backend/data/decision_training/<project>/`
- Live append: `backend/logs/decision_traces/`

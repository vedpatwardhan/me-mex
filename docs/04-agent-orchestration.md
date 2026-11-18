# Agent orchestration

> **Canon:** [00-vision-and-principles.md](./00-vision-and-principles.md) §5–6, §8. **Graph rules:** [03-graph-and-memory.md](./03-graph-and-memory.md).

LangGraph orchestrates **worker agents** (LLM + decision model) and **deterministic tools** (Mongo, staging, dock) behind LiveKit. **Conversation** does **not** mutate Mongo unless an agent invokes a **write tool** and you approve where required. **Gist**, **intra-doc**, **link/place**, and **reorg** are **separate** agent paths—not a v1 monolithic ingest.

---

## 1. Summary

| Concern | v2 choice |
|---------|-----------|
| User transport | **LiveKit** (audio + data for `context_json`) |
| Orchestration | **LangGraph** root graph + LangChain `create_agent` **worker agents** |
| Graph DB | **MongoDB** via **deterministic tools only** |
| Checkpointer | LangGraph session state—**plain JSON on disk** (per `thread_id`); **not** Mongo knowledge collections ([§12.2](./04-agent-orchestration.md#122-persistence-thread_id--checkpointer)) |
| Conversation | Supervisor / Conversation agent—**no write tools** unless routed |
| Retrieval / placement / reorg hops | **Gateway reranker DecisionScorer**: `query_node` + full `frontier` relevance vector; agent top‑k ([05 §3](./05-models-and-runtime.md#31-purpose--relevance-over-a-candidate-batch-replaces-v1-subgraph_expansion)) |
| Tools | **Deterministic only**—no LLM, no DecisionScorer, no embedder calls inside tool code ([§6](#6-deterministic-tools)) |
| Interactive runtime | **`astream_events` (v3)**, checkpointer + **`thread_id`**, **foreground/background context switch**, HITL only where graph writes need OK ([§12](#12-langgraph--langchain-runtime-interactive-agent)) |

---

## 2. Topology

```
[You] ←LiveKit audio/data→ [LiveKit Agent Worker]
                                    │
                                    ▼
                          LangGraph root StateGraph
                          (checkpointer on root only)
                                    │
              ┌─────────────────────┼─────────────────────┐
              ▼                     ▼                     ▼
     ContextPreprocessor      Supervisor            WorkflowObserver
     (deterministic)          create_agent          (deterministic: jobs ledger)
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼           ▼         ▼         ▼           ▼
   Conversation  GistWorker  IntraDoc  LinkPlace  ReorgWorker
   (no graph     Worker      Worker    Worker     Topology +
    writes)                           Partition  Retrieval
                                      + highlight
```

- **User-facing process** joins the LiveKit room; Mongo writes **only** through **deterministic tools** that agents invoke.
- **Supervisor** routes turns to **worker agents** (each may call Ministral and/or DecisionScorer, then tools—≤8 tools per agent step for Ministral tool-calling).
- **Conversation agent:** Q&A, summarize, spoken replies—**LLM in the agent**; fetch/highlight via deterministic tools only—**no graph writes** by default.

---

## 3. Request envelope

Every turn (voice or REST):

```json
{
  "text": "utterance",
  "context_json": {
    "active_project_id": "…",
    "selected_node_ids": ["…"],
    "constraints": {},
    "custom_fields": { "arxiv_id": "2510.12693", "reported_f1": "0.476" }
  }
}
```

**ContextPreprocessor** (deterministic, no LLM):

- Loads **project introduction / Genesis description** into prompt context (see §7).
- Merges canvas selection, constraints.
- **`custom_fields` authoritative** over conflicting STT in `text`.
- Seeds graph state for supervisor routing.

See [02-user-experience.md](./02-user-experience.md).

---

## 4. Human-in-the-loop and context rules

1. **Checkpointer on root graph only** — Session **`thread_id`** holds conversation + **job ledger**; worker subgraphs checkpoint long steps so work can **park** without blocking voice.
2. **Foreground always wins** — A new user turn routes the **user-facing** agent (Supervisor / Conversation) immediately. Long **background** workers **context-switch**: checkpoint, update `jobs`, **no OK required to pause** ([§12.5](#125-context-switching-foreground-vs-background)).
3. **HITL only for graph writes** — Dock **pending approval** only when Mongo would change—`interrupt()` preview and/or `enqueue_pending_approval` ([02](./02-user-experience.md) §4.2). Most checkpoints are **not** approval prompts.
4. **Writes after HITL** — Mutating tools resume only after you approve the matching dock item or voice token.
5. **No implicit ingest** — summary intent must **not** call write tools without explicit command or approved item.
6. **Barge-in** — Cancels **foreground** TTS/stream; **background jobs** keep running or move to `paused` unless you cancel the job.
7. **Project scoping** — every tool validates `active_project_id`.
8. **Status visibility** — `jobs` ledger + `list_pending_approvals`; ask “status of X?” without resuming background work.

---

## 5. Agents vs tools

| Layer | May call LLM / DecisionScorer / embedder? | Role |
|-------|-------------------------------------------|------|
| **Worker agent** (`create_agent` or dedicated graph node) | **Yes** — all model inference lives here | Route intent, run extract/summarize/score loops, speak, then call **deterministic tools** |
| **Tool** (LangChain `@tool` bound to workers) | **No** — must be **fully deterministic** given inputs | Mongo CRUD, staging I/O, dock queue, fetch/trafilatura, highlight ids, `interrupt` payloads |

**Forbidden:** a tool that internally calls Ministral, consolidation prompts, DecisionScorer, or embeddings. If v1 code mixed those, **split**: model steps stay in the **agent node**; persistence in **tools**.

**DecisionScorer** (cross-encoder—[05 §3](./05-models-and-runtime.md#3-decision-routing--cross-encoder-reranker)): `(query_node, frontier[])` → **relevance probabilities for every frontier node** via **`POST …/decision/score`** on the Colab gateway (replaces v1 generative **subgraph_expansion** hop). Agent applies **top‑k** after scoring. **HttpDecisionScorer** from workers; not a LangChain tool; not inside deterministic tools.

### 5.1 Worker agents (model work → tools)

| Agent | Model work (in agent, not in tools) | Typical deterministic tools after |
|-------|-------------------------------------|-----------------------------------|
| **Supervisor** | Turn routing, optional short reply | Delegates to workers |
| **Conversation** | Inquiry, summary, comparison, TTS script | `fetch_normalized_text`, `open_passages`, `get_suggested_next_actions` |
| **GistWorker** | Optional gist phrasing from your text | `create_or_update_root_gist`, `attach_source_uri`, `create_note`, `create_todo`, `promote_todo_to_concept_m` |
| **IntraDocWorker** | Chunk → extract → consolidate **LLM loop** (v1 prompts) | `fetch_normalized_text`, `upsert_staging_bundle`, `edit_staging_concept`, `enqueue_pending_approval`, `commit_intra_doc_graph` |
| **LinkPlaceWorker** | `query_node` = `ROOT`; frontier = hub/`INSIGHT` shortlist; full prob vector → dock | `enqueue_pending_approval`, `create_root_insight_edges` on approve |
| **ReorgRecommendWorker** | `query_node` = mutable node in question; frontier = relocation/split targets; full probs | `write_reorg_proposal`, `preview_reorg_diff`, `enqueue_pending_approval` |
| **ReorgApplyWorker** | None (plan already approved) | `apply_reorg_plan`, `split_section`, `relocate_under_parent`, … |
| **RetrievalWorker** | **Seed:** Genesis (or selected node). Bounded **BFS**: each hop `DecisionScorer(query, frontier_neighbors)` with **title + description** text → expand **top‑k**; then Ministral summary | `highlight_nodes`, `query_nodes_by_embedding`, `open_passages` |
| **ProjectScopeWorker** | Onboarding dialogue, scope draft text | `update_project_scope` |

Intra-doc **extract** is **not** a tool named `stage_intra_doc_concepts`; the **IntraDocWorker agent** runs the LLM pipeline, then **`upsert_staging_bundle`** + **`enqueue_pending_approval`** (“Review / commit intra-doc graph”).

Placement / reorg **suggest** is **not** a tool; the agent scores options, then tools **write proposals** to the dock.

---

## 6. Deterministic tools

Grouped by **effect**. Every entry is safe to call from pytest **without** mocking an LLM inside the tool.

### 6.1 Gist & scratch

| Tool | Effect |
|------|--------|
| `create_or_update_root_gist` | Create/update **`ROOT`** + gist from **provided** text |
| `attach_source_uri` | Bind URL/`file://` to existing `ROOT` |
| `create_note`, `create_todo` | Scratch nodes + links per args |
| `promote_todo_to_concept_m` | **ToDo** → **`CONCEPT_M`** (preserve links) |

### 6.2 Intra-document (persist only)

| Tool | Effect |
|------|--------|
| `fetch_normalized_text` | arXiv / trafilatura / local file → normalized text **string** (no LLM) |
| `upsert_staging_bundle` | Write replace staging JSON for `root_id` / pending URL |
| `edit_staging_concept` | Mutate staging row (rename/drop/split) per args |
| `enqueue_pending_approval` | Append dock item (staging, placement, reorg, gist, scope, …) |
| `commit_intra_doc_graph` | Write approved staging → `CONCEPT_I` + `passages` under **`root_id`** (`interrupt` + preview payload) |

### 6.3 Link / place

| Tool | Effect |
|------|--------|
| `create_root_insight_edges` | Add **`ROOT` ↔ hub/`INSIGHT`** links after approval |
| `highlight_nodes` | Set canvas highlight mask from `node_ids` |
| `query_nodes_by_embedding` | Mongo vector search given **precomputed** query vector + filters |
| `search_nodes_keyword` | Text index / regex search (no embedder) |

### 6.4 Reorg apply & topology

| Tool | Effect |
|------|--------|
| `write_reorg_proposal` | Store scored options blob from agent (no scoring here) |
| `preview_reorg_diff` | Format before/after struct from proposal (no Mongo write) |
| `apply_reorg_plan` | Commit approved plan |
| `split_section`, `merge_mutable_nodes`, `relocate_under_parent` | Single-step topology |
| `add_edge`, `remove_edge`, `update_edge_note` | Edge CRUD |
| `edit_mutable_node`, `rename_node`, `set_todo_status` | Mutable node CRUD |
| `delete_node`, `archive_node` | Destructive (`interrupt`) |

### 6.5 Evidence & dock

| Tool | Effect |
|------|--------|
| `open_passages` | Load `passages` by ids (token cap) |
| `get_suggested_next_actions` | Workflows graph nudges (deterministic rank) |
| `list_pending_approvals` | Merge `interrupt` + open approval rows for dock |

### 6.6 Project scope

| Tool | Effect |
|------|--------|
| `update_project_scope` | Write `introduction` + sync Genesis (`interrupt` optional) |

### 6.7 Guards (tool layer)

- `ImmutableNodeViolation` on illegal writes to `ROOT` evidence fields, `CONCEPT_I`, passages.
- Default: no auto edges from **`INSIGHT`** / hubs to `CONCEPT_I` (cite **`ROOT`** when linking sources).

---

## 7. Project lifecycle (create vs scope)

**Create project** — **UI/API only** ([06 P0](./06-workflows.md#p0--create-project-ui-only-no-agent-tool)). No LangGraph tool creates a workspace.

**Scope onboarding (P1)** — After you **unmute** on a project with empty scope ([06 P1](./06-workflows.md#p1--first-voice-project-scope-before-research)):

| Phase | Agent behavior |
|-------|----------------|
| **Incomplete scope** | **Conversation-only** (ProjectScope / supervisor): *“What is this project about?”* + follow-ups until **scope-complete** |
| **Scope-complete criteria** (agent judgment, not one-shot): **what** the work is; **where** it sits; **why** / goals; **what kinds of sources** you will explore (papers, topics, mixed paradigm)—enough to steer summaries and placement |
| **Ready to persist** | Agent proposes scope text → you confirm → **`update_project_scope`** (Mongo project + Genesis description) → *“What would you like next?”* |
| **Scope present** | Normal routing; **ContextPreprocessor** injects scope into every LLM prefix |
| **Scope update later** | Same conversation pattern or settings → `update_project_scope` |

Until scope is saved, **no** gist ROOT / intra-doc / link / reorg **writes** (inquiry and gist **talk** in dock OK). Scope does **not** create graph nodes beyond Genesis metadata.

**No `domain_mode`.** Scope text replaces any per-domain toggle.

---

## 8. Supervisor routing (intent → agent)

| User intent (examples) | Agent | Graph write? |
|------------------------|-------|--------------|
| Unmute on empty scope (P1) | ProjectScope conversation until criteria met | No (until `update_project_scope`) |
| arXiv + “what’s the gist?” (W2) | Conversation + fetch | No (ROOT via recommendation or explicit command) |
| “Summarize this link” | Conversation (+ `fetch_normalized_text`) | No |
| “Save that as gist” | GistWorker | Yes (ROOT) via tool |
| “Deepen this ROOT / build concept graph” | IntraDocWorker (LLM extract) → staging tools | Yes (after `commit_intra_doc_graph` approve) |
| “Where does this fit?” | LinkPlaceWorker (DecisionScorer) → dock → `create_root_insight_edges` | Only after approve |
| “Split this crowded hub” | ReorgRecommendWorker → `preview_reorg_diff` → ReorgApplyWorker | Yes (only after approve) |
| “What relates to X?” | RetrievalWorker (scorer hops + summary) → `highlight_nodes` | No (highlight only) |

Plain-language persist commands map here; non-trivial diffs use `interrupt(response_schema=...)`.

---

## 9. LangGraph vs v1

| v1 | v2 |
|----|-----|
| `ExecutiveOrchestrator.classify_intent` | Supervisor + worker **agents** |
| Monolithic ingest path | Separate agents + **deterministic** tools |
| `GraphNavigator.subgraph_expansion` LLM chain | **RetrievalWorker agent** + DecisionScorer + `highlight_nodes` |
| Auto `reorganize_overclustered_nodes` | **ReorgRecommendWorker** + approved `apply_reorg_plan` |
| `POST /api/chat` scrollback | LiveKit + recommendations dock; optional REST same `thread_id` |
| `chat_messages` as UX | Minimal audit log only |

---

## 10. API boundaries

- **LiveKit:** audio, `context_json`, approval tokens (`approve` / `cancel`).
- **REST (parallel):** graph CRUD + agent turn for pytest/headless.
- **SSE:** thin graph events (highlights, interrupts)—not full chat prose stream.

---

## 11. Observability

- Append-only **`decision_traces`** (live + bootstrap) for eval and optional reranker fine-tune — [07-performance-and-observability.md](./07-performance-and-observability.md).
- Tool-call log per session `thread_id`.
- LangSmith / OTEL optional.

---

## 12. LangGraph & LangChain runtime (interactive agent)

The user-facing agent must stay **responsive** while **long jobs** (intra-doc extract, scorer batches) run and while **multiple asks** can overlap across a session. Use **LangGraph 1.x / LangChain 1.x** primitives as the standard runtime—not bespoke polling alone.

**Doc anchors:** [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts), [checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers), [streaming](https://docs.langchain.com/oss/python/langgraph/streaming), [event streaming (v3)](https://docs.langchain.com/oss/python/langgraph/event-streaming), [Send / Command](https://docs.langchain.com/oss/python/langgraph/graph-api-send-command), [create_agent](https://reference.langchain.com/python/langchain/agents/create_agent).

### 12.1 Composition

| Piece | Role in Me-Mex |
|-------|----------------|
| **Root `StateGraph`** | `ContextPreprocessor` → `Supervisor` → worker subgraphs → `WorkflowObserver`; owns **session state**, checkpointer, job ledger |
| **`create_agent` subgraphs** | One compiled graph per worker (Conversation, Gist, IntraDoc, …); **nested** under root; optional **middleware** for project scope injection |
| **Deterministic tools** | Bound to worker agents only; called from agent nodes after model steps |
| **LiveKit worker** | `asyncio` loop: `graph.astream_events(..., version="v3")` → token stream to TTS; data channel → dock |

Workers are **LangGraph subgraphs** (each may be `create_agent(...)`). Root graph **does not** hide LLM inside tools.

### 12.2 Persistence: `thread_id` + checkpointer

- **`configurable.thread_id`** = stable session pointer (LiveKit room + user + project, or explicit `context_json.session_id`). Reuse across mute/unmute and dock-only turns.
- **Checkpointer on root compile only** (per §4)—workers invoked as subgraphs inherit checkpoint namespace from parent unless explicitly stateless.
- **Implementation (committed):** **Plain JSON files on disk** on the **local** machine where LangGraph runs—one directory tree keyed by `thread_id` (e.g. `backend/data/checkpoints/<thread_id>/…`), each file a LangGraph-serialized checkpoint (messages, channel state, `jobs`, interrupt metadata). **No** checkpoint data in MongoDB `nodes`/`edges`/`projects`. (Ministral/vLLM on Colab is stateless HTTP from the agent’s perspective.)
  - **pytest:** in-memory saver or ephemeral temp JSON dir.
  - **Not in scope for v2:** Mongo/Postgres/SQLite checkpointers unless ops later outgrow single-user file storage ([10 A2](./10-open-questions.md#6-resolved-decisions-locked)).
- Graph **data** (knowledge) remains **MongoDB** via tools only; checkpoints are **session/ephemeral-leaning** files with a different lifecycle than research nodes.
- **Durability:** Prefer `"async"` or `"sync"` checkpoint durability during long **IntraDoc** runs so a process crash can resume mid-pipeline ([durability modes](https://docs.langchain.com/oss/python/langgraph/checkpointers)).
- **`get_state` / `update_state`:** Optional dev APIs to inspect or patch checkpoint (e.g. user edits staging in dock → `update_state` before `Command(resume=)`).

**LiveKit worker (always-on):** Separate **long-lived** agent process (or supervised thread group) running the root LangGraph + room subscription—not one FastAPI request worker per user. FastAPI serves REST/graph; worker owns `astream_events` + TTS/STT bridge. Deploy topology: separate process **preferred** if restarts/GPU differ; co-process OK if simpler ([10 §6 A1](./10-open-questions.md#6-resolved-decisions-locked)).

### 12.3 Streaming → dock + voice (interactivity)

**Primary API:** `graph.astream_events(input, config, version="v3")` (recommended over legacy `stream_mode` only).

| Projection | UX |
|------------|-----|
| **`stream.messages`** | LLM tokens → recommendations dock “latest response” + Kokoro TTS (incremental) |
| **`stream.custom`** / **`get_stream_writer`** | Fine-grained status: `{"job_id": "…", "phase": "extract", "chunk": "4/12"}` → dock + job ledger |
| **`stream.tasks`** | Native task start/finish (parallel `Send`, subgraph steps) → worker badges |
| **`stream.values`** | Full state snapshots after supersteps → sync `jobs` list to UI |
| **`stream.interrupted` / `stream.interrupts`** | **HITL only** when a write needs OK → dock approval row; background **park** on context switch usually **does not** surface here (use `jobs` + `custom` instead) |
| **`stream.subgraphs`** | Which worker subgraph is active (“IntraDocWorker”, “LinkPlaceWorker”) |

Also enable **`stream_mode=["updates", "custom", "tasks"]`** on the root graph when not using v3 wrappers in tests.

**Rule:** Anything the user should see **while waiting** flows through **custom stream** and/or **`tasks`**—not only the final agent message.

### 12.4 Tracking what the user asked for (job ledger)

Root state includes an append-only or reducer-backed **`jobs`** list (name TBD in implementation):

| Field | Purpose |
|-------|---------|
| `job_id` | Correlate utterance → work → dock recommendation |
| `kind` | `inquiry` \| `intra_doc` \| `gist` \| `placement` \| `reorg` \| `retrieval` \| `scope` |
| `label` | Short user-facing text (“Deep read ERA ROOT”) |
| `status` | `queued` → `running` → `awaiting_approval` → `done` \| `cancelled` \| `error` |
| `worker` | Subgraph name for badges |
| `recommendation_id` | Link to dock approval item when waiting |
| `progress` | Optional string from `get_stream_writer` |

**WorkflowObserver** (deterministic graph node after each superstep):

- Merges `stream.tasks` / tool results into `jobs`.
- Refreshes **`get_suggested_next_actions`** inputs.
- Does **not** call LLMs.

Supervisor / Conversation agents answer “what happened to my deep read?” by reading **`jobs`** + `list_pending_approvals` from state/tools.

### 12.5 Context switching (foreground vs background)

**Problem:** Intra-doc extract and similar jobs can run **minutes**. The user must keep talking—new summaries, other papers, status questions—without waiting for a global graph freeze.

| Layer | Behavior |
|-------|----------|
| **Foreground** | Supervisor + Conversation on **every new utterance**; streams reply + handles barge-in. This is the “user-facing agent.” |
| **Background** | Heavy worker subgraphs (**IntraDocWorker**, long placement/reorg scoring) registered as **`jobs`** with their own progress streams. |
| **On context switch** | User changes topic or selects another ROOT → foreground routes the **new** intent; background job **parks** at last checkpoint (`jobs.status` → `paused` or stays `running` if safe to continue in parallel). **No approval** required to switch context. |
| **Resume background** | User returns (“continue the ERA deep read”) → supervisor routes to same `job_id`; `Command(resume=…)` or new invocation loads checkpoint and continues. |
| **Completion** | When background **finishes extract**, it **does not** auto-commit; it enqueues dock **review** (HITL)—that step *does* need your OK. |

**Implementation patterns (pick one or combine):**

1. **Parallel asyncio tasks** — Foreground `astream_events` per turn; background job = separate graph invoke with `job_id` in config metadata; checkpointer stores both under session `thread_id` + job subkeys.
2. **Checkpoint park** — Background superstep ends; state saved; foreground graph turn proceeds on same `thread_id` without draining background (LangGraph durable execution).
3. **Cancel foreground only** — Barge-in stops TTS and the **current** conversational stream; background extract continues unless you cancel the job explicitly.

**Not the goal:** treating every checkpoint or graph pause as “approve to continue.” Context switches are **automatic** coordination, not HITL.

### 12.6 Human-in-the-loop: `interrupt` + `Command(resume=)` (graph writes only)

Use LangGraph **`interrupt()`** only when **you** must decide on a **persist** action:

- Staging **commit**, placement **edges**, reorg **apply**, destructive delete, large scope write.

Flow:

- Tool/agent calls **`interrupt(payload)`** with JSON preview (staging list, diff, gist text).
- Foreground may already be on another topic; payload lands in **`list_pending_approvals`** / dock—not blocking voice.
- When you approve: `graph.astream_events(Command(resume=approve_payload), config, version="v3")` with the **same `thread_id`** (and `job_id` if tied to a background job).
- **`response_schema`** when approve shape must be validated.

**Note:** Resuming **re-executes the node from the start**; keep heavy LLM **before** `interrupt`, or idempotent tools.

Prefer **dynamic `interrupt()`** for HITL only—not for parking background work on context switch.

### 12.7 Async, parallel, fault tolerance

| Feature | Use |
|---------|-----|
| **`ainvoke` / `astream` / `astream_events`** | LiveKit agent must not block the event loop on graph runs |
| **`Send`** | IntraDoc **map** steps (per-chunk extract) in parallel with reducer merge into staging—fan-in before `enqueue_pending_approval` |
| **`RetryPolicy`** | On `fetch_normalized_text` node and Colab vLLM hop—not on Mongo writes |
| **Parallel supersteps** | Fault-tolerant: failed branch retries without re-running successful siblings (checkpointer) |
| **Barge-in** | Cancel current graph task; set in-flight `jobs` to `cancelled`; do not auto-resume cancelled job without new user intent |

### 12.8 LangChain agent middleware (optional v2)

`create_agent(..., middleware=[...])` for cross-cutting concerns **without** hiding them in tools:

- Inject **project scope** into every model call
- Trim / summarize **messages** when topic thread grows (distinct from graph ToDos)
- Emit **custom stream** events on tool start/end

### 12.9 Feature checklist (use / defer)

| LangGraph / LangChain capability | Me-Mex v2 |
|----------------------------------|-----------|
| Root `StateGraph` + subgraph workers | **Use** |
| `create_agent` per worker | **Use** |
| Checkpointer + `thread_id` | **Use** (session memory + **park** background jobs on context switch) |
| `interrupt` + `Command(resume=)` | **Use** (HITL graph writes only—not every pause) |
| `astream_events` v3 | **Use** (dock + TTS; HITL when `stream.interrupted`) |
| Foreground/background split | **Use** (interactive voice while long jobs run) |
| `get_stream_writer` / `custom` stream | **Use** (progress + job status) |
| `tasks` / `updates` stream modes | **Use** (badges, debugging) |
| `Send` map-reduce | **Use** (intra-doc chunks) |
| `RetryPolicy` | **Use** (fetch / remote LLM) |
| Checkpoint durability `async`/`sync` | **Use** on long jobs |
| `get_state` / `update_state` | **Use** (dock edit → resume) |
| `Command(update=...)` from tools | **Use** sparingly to patch state (e.g. user_info)—prefer root reducers |
| `store` (long-term memory) | **Defer**—Mongo graph + `jobs` + `decision_traces` suffice for v2 |
| Time-travel / fork UI | **Defer**—checkpoints for ops/debug only |
| Static breakpoints | **Defer**—dynamic `interrupt` only |

### 12.10 LiveKit bridge (implementation sketch)

```
User audio → STT → text + context_json
       → foreground: astream_events (thread_id = session) → dock + TTS
       → background: optional parallel job (job_id) → custom/tasks → jobs ledger
New user turn (context switch) → foreground routes new intent; background parks/checkpoints (no approval)
Background done extract → enqueue dock HITL row (approve commit)
User "approve 2" / tap → Command(resume=…) for that HITL item only
Barge-in → stop foreground TTS/stream; background unchanged unless user cancels job
```
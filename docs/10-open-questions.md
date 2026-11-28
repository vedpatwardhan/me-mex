# Open questions

> **Canon:** Locked choices live in [00-vision-and-principles.md](./00-vision-and-principles.md) §8. **Resolved** decisions are in [§6](#6-resolved-decisions-locked). This file lists **remaining** gaps only.

---

## 1. Architecture

| # | Status |
|---|--------|
| A1 | **Resolved** — [§6](#6-resolved-decisions-locked) |
| A2 | **Resolved** — [§6](#6-resolved-decisions-locked) |
| A3 | **Resolved** — [§6](#6-resolved-decisions-locked) |
| A4 | **Resolved** — [§6](#6-resolved-decisions-locked) |

---

## 2. User experience

| # | Status |
|---|--------|
| U1 | **Resolved** — [§6](#6-resolved-decisions-locked) |
| U2 | **Resolved** — [§6](#6-resolved-decisions-locked) |
| U3 | **Resolved** — [§6](#6-resolved-decisions-locked) |
| U4 | **Open** — Freeform key/value vs per-project **pinned** field keys (session pin UX) |
| U5 | **Resolved** — [§6](#6-resolved-decisions-locked) |
| U6 | **Resolved** — [§6](#6-resolved-decisions-locked) |

---

## 3. Models and runtime

| # | Status |
|---|--------|
| M1 | **Resolved** — [§6](#6-resolved-decisions-locked) |
| M2 | **Open** — One global reranker checkpoint vs per-project fine-tune on gateway |
| M3 | **Resolved** — [§6](#6-resolved-decisions-locked) |
| M4 | **Resolved** — [§6](#6-resolved-decisions-locked) |
| V1 | **Open** — `DOCK_STREAM_MAX_TOKENS` default ([04 §12.11](./04-agent-orchestration.md#1211-conversation-first-voice-normative)) |
| V2 | **Resolved** — Proactive TTS on job `done` / `awaiting_approval` is **always on** when unmuted ([04 §12.12](./04-agent-orchestration.md#1212-proactive-updates-blend-in)) |
| V3 | **Open** — Conversation endpoint placement: backend stream vs Colab hop for plane 1 LLM |
| V4 | **Open** — Keyword-first `route_intent` on dispatch-only path for latency |

---

## 4. Product / graph

| # | Status |
|---|--------|
| P1 | **Resolved** — [§6](#6-resolved-decisions-locked) |
| P2 | **Deferred** — Other-project custom importers not v2; robotics three-file bootstrap only |
| P3 | **Resolved** — [§6](#6-resolved-decisions-locked) |

---

## 5. Background: feasibility doc corrections

| `memex_rebuild_feasibility_and_plan.md` assumed | Spec intent |
|--------------------------------------------------|-------------|
| Pipecat-first voice | **LiveKit** |
| Clean-slate SQLite dual-graph | **MongoDB** knowledge graph |
| 5-day greenfield | Phased v2 per [09-phasing.md](./09-phasing.md) |
| LoRA deferred (no Day-1 data) | **Off-the-shelf reranker** + bootstrap for **eval**; optional fine-tune from traces |
| 27 tools one supervisor | **Composable tools** + workers, HITL |
| Scrollback / no mute browsing | **Latest-message panel** + mute + graph-first |

Add new open items inline in §1–4 as implementation discovers gaps.

---

## 6. Resolved decisions (locked)

### Architecture

| ID | Decision |
|----|----------|
| **A1 LiveKit worker** | **Always-on** LiveKit agent process (background). **Not** tied to per-request FastAPI workers. May be a **separate OS process** or co-located with FastAPI—pick whichever is **cleanest to operate** (lifecycle, restarts, GPU affinity). Frontend connects **room ↔ agent ↔ graph tools**. FastAPI remains REST/graph CRUD; voice path goes through the agent worker. |
| **A2 Checkpointer** | **Plain JSON on disk** (per `thread_id`), **not** near the Mongo knowledge graph. Agent/session state only—see [04 §12.2](./04-agent-orchestration.md#122-persistence-thread_id--checkpointer). Layout: [07 §7](./07-performance-and-observability.md#7-logging-layout-proposed). |
| **A3 Backend layout** | **`me-mex` v2 is a full remake** in place; tag **`v1`** preserves old code. Remove or replace v1 code freely; **reuse from v1 only when useful** ([08](./08-migration-and-reuse.md)). No `backend_v2/` split required. |
| **A4 Workflows / nudges memory** | **No** separate workflows-graph Mongo collection or JSON sidecar for ML. **Dock nudges** are computed from graph state + session; **training signal** for routing lives in **`decision_traces`** (bootstrap JSONL + live append)—same schema family as [05 §8](./05-models-and-runtime.md#8-decision-trace-schema-training--eval). Optional short-lived session cache for ranking nudges is implementation-only, not a persisted “workflows graph” product store. |

### User experience

| ID | Decision |
|----|----------|
| **U1 Canvas** | Keep **v1-style drawing** (`react-force-graph-2d`, structure key, prewarm/pin, `cooldownTicks={0}`) per [02 §5.4](./02-user-experience.md#54-layout-and-rendering-performance-carry-forward-from-v1). **v2 node kinds** change colors/labels only—not the layout engine. **One** graph; **filters/toggles** to show/hide kinds—not separate “catalog/insights” tabs or views. Section hulls: **deferred**. |
| **U2 Direct manipulation** | **Not voice-only MVP.** Full **UI** graph ops: delete node/edge, select, pin/drag as in v1 patterns. **Placement/link** to new targets still via **voice, dock recommendations, or agent-assisted** flows—not silent auto-wiring from canvas alone. Manual deletes may **trigger** recommendations ([06 W12](./06-workflows.md#11-w12--manual-graph-edits-canvas)). |
| **U3 Input model** | **Primary:** voice (transcript). **Parallel:** **custom fields** for exact values (URLs, arXiv ids, metrics, `root_id`)—like code + env vars. No reliance on hidden type-only box for MVP; optional advanced JSON drawer remains. |
| **U5 LiveKit room** | **Single room** model—no room-per-project, **no** multi-user / cross-project LiveKit concurrency. Project switch = **`active_project_id` in `context_json`** + UI reload; same agent session pattern. |
| **U6 Project intro** | **P1 voice** collects scope; **dock shows** stored project intro/description so you can read what was saved. Re-edit via conversation + `update_project_scope` or settings later. |

### Models and runtime

| ID | Decision |
|----|----------|
| **M1 STT/TTS + GPU** | **Colab (one VM):** **inference gateway** — Ministral 3 8B **vLLM** (GPU), **cross-encoder reranker** + Whisper + Kokoro (**CPU**). **Local:** LangGraph agents, LiveKit, Mongo, checkpoint JSON, UI. Single public URL for chat, `decision/score`, STT/TTS. |
| **M3 Bootstrap dataset** | Build decision JSONL by **joining tier files** (`overall_insights`, `deeper_read_notes`, …) → `query_node` / `frontier` / **`label_relevance`** for **eval** and optional reranker fine-tune—not an isolated “parenthetical parser” problem. |
| **M4 Placement UX** | **Suggest-only** for v2 focus—ranked candidates in dock; **no** auto-propose edge diff above threshold; revisit visual “factory” later. |

**Pivot (2026-11-18):** Production routing = **cross-encoder on gateway**; **LoRA-on-Ministral decision** and **generative JSON decision hops** superseded. See [05-models-and-runtime.md](./05-models-and-runtime.md), [reports/2026-11-18-retrieval-methods.md](../reports/2026-11-18-retrieval-methods.md).

### Product / graph

| ID | Decision |
|----|----------|
| **P1 Partitions** | **Neither** fuzzy weighted membership nor a separate tag system. **Plain graph:** uniform edges; importance via **topology** (e.g. **degree** on mutable hubs) for **reorg recommendations** only ([03 §9](./03-graph-and-memory.md#9-partitions-and-crowded-sections)). |
| **P3 Deploy** | **`me-mex` only** deploy target; `cortex-os` is a container folder. **dev** vs **prod** environments OK; single product repo. |

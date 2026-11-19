# Phasing (full spec → v2 delivery)

> **Canon:** [00-vision-and-principles.md](./00-vision-and-principles.md) §8–9. This document is the **implementation rollout map** for all of `me-mex/docs/`—not a thin summary. Use the **coverage matrices** below to verify nothing shipped without a phase home; use **phase sections** for ordered delivery and exit checks.

Unresolved build choices: [10-open-questions.md](./10-open-questions.md) (gating table in [§12](#12-open-questions--phase-gates)).

---

## 1. Overview

```
Phase 0  Spec aligned (00–11) + coverage matrix maintained in this file
    ↓
Phase 1  Mongo schema + all deterministic tools + headless agents + gateway reranker + bootstrap JSONL
    ↓
Phase 2  LangGraph interactive runtime + LiveKit + full UX shell + all workflows voice/panel
    ↓
Phase 3  Markdown import to graph + multi-project seed + decision dataset refresh
    ↓
Phase 4  Live decision traces + optional reranker refresh + observability completion + UX polish
    ↓
Phase 5  Hardening (load scenarios, v1 fence, soak)
```

**Invariants throughout:** no implicit graph ingest; no autonomous overnight co-scientist; MongoDB; **cross-encoder decision routing via Colab gateway** (no generative LLM hops; no LoRA decision MVP); Whisper base.en (Colab CPU); edge-tts; LiveKit; recommendations **initiate** guided flows—**no** silent graph writes ([06 §0](./06-workflows.md#0-how-recommendations-work-all-workflows)); v1 reuse **only when aligned** ([08](./08-migration-and-reuse.md) reuse doctrine).

---

## 2. Master coverage matrix (spec → phase)

Legend: **P0–P5** = phase; **—** = reference only, no implementation row; **ongoing** = starts in listed phase, continues later.

| Source | Topic | Primary phase | Notes |
|--------|--------|---------------|--------|
| [00](./00-vision-and-principles.md) §1–7 | Vision, tiers, principles | P0 canon | Build rules in all phases |
| [00](./00-vision-and-principles.md) §8 | Platform stack (committed) | P1–P2 | Reranker + gateway P1; voice P2 |
| [00](./00-vision-and-principles.md) §9 | Success criteria | P1–P5 | [§3](#3-success-criteria-00-9--phases) |
| [01](./01-v1-baseline.md) | v1 reference / gaps | — | Tag `v1` only; informs [08](./08-migration-and-reuse.md) |
| [02](./02-user-experience.md) §2–3 | Layout, voice rail, P0 API entry | P2 | Minimal project API stub P1 for pytest |
| [02](./02-user-experience.md) §4 | Recommendations dock (nudges + approvals) | P2 | Polish P4 |
| [02](./02-user-experience.md) §5 | Canvas, legend, layout perf §5.4 | P2 | Legend polish P4; layout P2 |
| [02](./02-user-experience.md) §6–7 | Request envelope, UX invariants | P2 | REST mirror P1 |
| [03](./03-graph-and-memory.md) §2–6 | Tiers, ROOT rule, kinds, edges | P1 schema + tools | Import P3 |
| [03](./03-graph-and-memory.md) §7 | Staging contract | P1 | Staging cache P2+ |
| [03](./03-graph-and-memory.md) §8–9 | Multi-project, partitions/reorg | P2 / P5 soak | Partitions detail P2 reorg path |
| [03](./03-graph-and-memory.md) §10 | Nudges vs `decision_traces` | P2 dock nudges; P1/P4 traces | No workflows-graph collection |
| [04](./04-agent-orchestration.md) §3–6 | Envelope, HITL, agents, tools | P1 tools; P2 agents | Full catalog [§5](#5-agents-and-deterministic-tools--phases) |
| [04](./04-agent-orchestration.md) §7–8 | P0/P1 lifecycle, routing table | P2 | P0 API P1 stub |
| [04](./04-agent-orchestration.md) §10–11 | API boundaries, observability hooks | P1 REST; P2 LiveKit | Traces P4 |
| [04](./04-agent-orchestration.md) §12 | LangGraph runtime (stream, jobs, park) | P2 | Required for voice UX |
| [05](./05-models-and-runtime.md) §1–3 | Stack, DecisionScorer, bootstrap | P1 gateway reranker; P2 inference | |
| [05](./05-models-and-runtime.md) §4 | Embeddings | P1 retrieval tests; P2 agent | |
| [05](./05-models-and-runtime.md) §5–6 | Speech, Colab topology | P2 | M1 hosting [10](./10-open-questions.md) |
| [05](./05-models-and-runtime.md) §7–8 | Latency targets, trace schema | P1 eval; P4 live append | |
| [06](./06-workflows.md) | P0, P1, W2–W11, anti-patterns | P1–P5 | [§4](#4-user-workflows-06--phases) |
| [07](./07-performance-and-observability.md) | Perf, instrumentation, caches, load | P2 partial; P4–P5 full | [§8](#8-performance-and-observability-07--phases) |
| [08](./08-migration-and-reuse.md) | Optional v1 reuse, import, flags | P1 flags; P3 import | No misaligned ports |
| [10](./10-open-questions.md) | Unresolved | Gates [§12](#12-open-questions--phase-gates) | |
| [references](./references.md) | Pointers | — | Fixtures for P1/P3 |
| [11](./11-testing.md) | Unit / integration / e2e / CI | P1–P5 gates | Every tool, agent, workflow |

---

## 3. Success criteria (00 §9) → phases

| Criterion ([00 §9](./00-vision-and-principles.md#9-success-criteria-personal-research)) | Must pass by |
|------------------------------------------------------------------------------------------|--------------|
| Summary without mutation; optional promote note/ToDo | P2 (W9, W6) |
| ToDo → `CONCEPT_M` when work resumes | P2 (W6b) |
| Short thread → commit (paper + concepts + edges) | P2 (W7) |
| Catalog at scale (many gist ROOTs, no auto extract/reorg) | P1 gist tools + P2 voice |
| Deep read one paper through staging | P1 commit path + P2 W3 all paths |
| Placement “where does this fit?” + you wire ROOT | P1 reranker + P2 LinkPlace HITL |
| Insights tree via approved reorg diff | P1 preview + P2 W5 |
| Retrieval highlighted subgraph, bounded hops | P1 reranker + P2 RetrievalWorker |
| Voice + canvas + recommendations dock | P2 |
| Multi-project isolated graphs + switch | P2 switcher + P5 soak |
| Decision quality — bootstrap eval / gateway smoke (optional gate) | P1 exit |

---

## 4. User workflows (06) → phases

| Workflow | Spec | Phase 1 (headless / pytest) | Phase 2 (voice + panel) | Later |
|----------|------|-----------------------------|-------------------------|--------|
| **§0** Recommendations initiate only | [06 §0](./06-workflows.md#0-how-recommendations-work-all-workflows) | `enqueue_pending_approval` + no auto-write tests | Dock nudge vs approval classes [02 §4.2](./02-user-experience.md) | P4 nudge logging |
| **P0** Create project (API only) | [06 P0](./06-workflows.md#p0--create-project-ui-only-no-agent-tool) | REST create project + empty scope | Top bar + “unmute when ready” | — |
| **P1** Scope onboarding | [06 P1](./06-workflows.md#p1--first-voice-project-scope-before-research) | — | ProjectScopeWorker + first unmute | Scope edit in settings |
| **W2** Gist inquiry (no ROOT until commit) | [06 W2](./06-workflows.md#2-w2--gist-inquiry-no-root-yet) | Conversation mock + gist tools; direct ROOT command | Full thread + “create ROOT” recommendation | — |
| **W3a** Deep read after long paper thread | [06 W3a](./06-workflows.md#w3a--recommended-after-long-paper-thread) | Staging + commit under ROOT | Dock deep-read nudge | — |
| **W3b** Deep read existing gist ROOT | [06 W3b](./06-workflows.md#w3b--existing-gist-root-on-canvas) | Same staging keyed `root_id` | Selection + `custom_fields.root_id` | — |
| **W3c** Direct URL deep read | [06 W3c](./06-workflows.md#w3c--direct-deep-read-url--command) | fetch + staging | Voice + fields | — |
| **W4a** Link recommendation after new node | [06 W4](./06-workflows.md#4-w4--connect--link-nodes) | LinkPlace + reranker + approve edges | Dock placement approval | — |
| **W4b** Manual link | [06 W4b](./06-workflows.md#w4b--manual-agent-may-not-have-suggested-it) | `create_root_insight_edges` | Voice + selection context | — |
| **W5** Reorganization | [06 W5](./06-workflows.md#5-w5--reorganization) | preview + apply with interrupt | ReorgRecommend + crowded-hub nudge | — |
| **W6** Note / ToDo capture | [06 W6](./06-workflows.md#6-w6--capture-note--todo) | `create_note`, `create_todo` | Voice | — |
| **W6b** Promote ToDo → `CONCEPT_M` | [06 W6b](./06-workflows.md#6-w6--capture-note--todo) | `promote_todo_to_concept_m` | Voice + recommendation optional | — |
| **W7** Rich commit after thread | [06 W7](./06-workflows.md#7-w7--rich-commit-after-thread) | Multi-tool approval chain | Voice orchestration | — |
| **W8** Muted browsing | [06 W8](./06-workflows.md#8-w8--muted-browsing) | — | Mute = no uplink; canvas/fields work | — |
| **W9** Summary only (no graph) | [06 W9](./06-workflows.md#9-w9--summary-only-no-graph) | Conversation-only pytest | Conversation agent | — |
| **W11a** Retrieval on ask | [06 W11a](./06-workflows.md#w11a--you-ask-primary) | RetrievalWorker + highlight | Voice + canvas highlight | — |
| **W11b** ToDo relevance nudge | [06 W11b](./06-workflows.md#w11b--todo-relevance-optional-recommendation) | `get_suggested_next_actions` stub | Informational dock row | — |
| **W12** Manual canvas delete/disconnect | [06 W12](./06-workflows.md#11-w12--manual-graph-edits-canvas) | REST delete + event to agent | Reconnect/reorg nudges | — |
| **§11** Anti-patterns | [06 §11](./06-workflows.md#11-anti-patterns-must-not-happen) | CI / manual checklist | P5 fence v1 paths | Ongoing |

---

## 5. Agents and deterministic tools → phases

### 5.1 Worker agents ([04 §5.1](./04-agent-orchestration.md#51-worker-agents-model-work--tools))

| Agent | P1 | P2 |
|-------|----|----|
| **Supervisor** | Headless routing tests | LiveKit turns + `astream_events` |
| **Conversation (voice plane 1)** | W2/W9 REST harness | Dialogue only; dispatch workers — **must match** [04 §12.11–12.13](./04-agent-orchestration.md#1211-conversation-first-voice-normative) before voice gate green |
| **WorkflowAgent** | — | Dock card LLM (§12.4b) + proactive TTS (§12.12) |
| **GistWorker** | Gist/attach/note/todo tools | W2 commit + W6 |
| **IntraDocWorker** | Extract harness → staging → commit | W3 + dock staging row + job progress |
| **LinkPlaceWorker** | Reranker + placement enqueue | W4 + dock approval |
| **ReorgRecommendWorker** | Proposal + preview | W5 + crowded hub nudge |
| **ReorgApplyWorker** | `apply_reorg_plan` after approve | Same |
| **RetrievalWorker** | BFS + reranker + highlight | W11a |
| **ProjectScopeWorker** | — | P1 onboarding |

### 5.2 Deterministic tools ([04 §6](./04-agent-orchestration.md#6-deterministic-tools))

**Phase 1 — implement and pytest every tool** (no LLM inside tools):

| Group | Tools |
|-------|--------|
| Gist & scratch | `create_or_update_root_gist`, `attach_source_uri`, `create_note`, `create_todo`, `promote_todo_to_concept_m` |
| Intra-doc | `fetch_normalized_text`, `upsert_staging_bundle`, `edit_staging_concept`, `enqueue_pending_approval`, `commit_intra_doc_graph` |
| Link / place | `create_root_insight_edges`, `highlight_nodes`, `query_nodes_by_embedding`, `search_nodes_keyword` |
| Reorg & topology | `write_reorg_proposal`, `preview_reorg_diff`, `apply_reorg_plan`, `split_section`, `merge_mutable_nodes`, `relocate_under_parent`, `add_edge`, `remove_edge`, `update_edge_note`, `edit_mutable_node`, `rename_node`, `set_todo_status`, `delete_node`, `archive_node` |
| Evidence & dock | `open_passages`, `get_suggested_next_actions`, `list_pending_approvals` |
| Project | `update_project_scope` |
| Guards | `ImmutableNodeViolation`; default no auto INSIGHT→`CONCEPT_I` |

**Phase 2** — wire all tools to dock approval types [02 §4.2](./02-user-experience.md), LiveKit `approve`/`cancel`, LangGraph `interrupt()` + `Command(resume=)`.

---

## 6. Graph, memory, and UX → phases

| Deliverable | Spec | Phase |
|-------------|------|-------|
| Mongo collections + v2 fields (`introduction`, staging pointers, `node_kind`, edge `note`, ToDo `status`) | [03 §1](./03-graph-and-memory.md#1-summary), [08 §2](./08-migration-and-reuse.md#2-committed-persistence) | P1 |
| Canvas node kinds + single edge kind | [03 §5–6](./03-graph-and-memory.md#5-canvas-node-kinds) | P1 model; P2 render |
| ROOT-only insight links | [03 §3](./03-graph-and-memory.md#3-linking-rule-insights--document-root-only) | P1 tools + tests |
| Staging-only deep read; no bundle ingest | [03 §7](./03-graph-and-memory.md#7-staging-intra-document-tool-only) | P1 |
| Deepen gist ROOT (same `root_id`) | [03 §7](./03-graph-and-memory.md#7-staging-intra-document-tool-only), [08 §6](./08-migration-and-reuse.md#6-deepen-existing-gist-root-migration-note) | P1 + P2 W3b |
| Multi-project isolation | [03 §8](./03-graph-and-memory.md#8-multiple-projects) | P1 data; P2 UI; P5 soak |
| Partitions / crowded sections → reorg rec | [03 §9](./03-graph-and-memory.md#9-partitions-and-crowded-sections) | P2 W5 |
| Dock nudges (no workflows-graph DB) | [03 §10](./03-graph-and-memory.md#10-nudges-vs-training-traces) | P2; training = `decision_traces` |
| Three-tier markdown mapping | [03 §11](./03-graph-and-memory.md#11-markdown-habit--graph-corrected) | P3 import |
| Voice rail + custom fields authoritative | [02 §3](./02-user-experience.md#3-voice-rail) | P2 |
| Dock: latest response + jobs + recommendations | [02 §4](./02-user-experience.md#4-recommendations-dock-default-not-optional) | P2 |
| Color legend (all kinds) | [02 §5.2](./02-user-experience.md#52-color-and-label-legend-v2) | P2 MVP; P4 polish |
| Structure-key layout (no thrash) | [02 §5.4](./02-user-experience.md#54-layout-and-rendering-performance-carry-forward-from-v1), [07 §4](./07-performance-and-observability.md#4-frontend-graph-canvas) | P2 carry v1 pattern |
| Context JSON envelope | [02 §6](./02-user-experience.md#6-request-payload) | P1 REST; P2 LiveKit |
| Feature flags off v1 auto paths | [08 §8](./08-migration-and-reuse.md#8-feature-flags-transition) | P1 new projects |

---

## 7. Models and runtime (05) → phases

| Deliverable | Phase |
|-------------|-------|
| Ministral 3 8B on Colab vLLM (chat + tools) | P1 for IntraDoc harness; P2 production agent path |
| Bootstrap parser → `decision_training/<project>/*.jsonl` | P1 |
| Held-out eval on `query_node` + full `frontier` labels | P1 **exit gate** |
| Gateway `decision/score` (cross-encoder); four-model Colab stack | P1 |
| ContextPreprocessor project scope in prompts | P2 (after P1 `update_project_scope`) |
| Embeddings in agents (`query_nodes_by_embedding`) | Optional P3+; stub OK through P2 |
| Whisper base.en (Colab) + edge-tts + VAD; LiveKit same `thread_id` | P2 |
| Speech barge-in cancels in-flight TTS / unsafe writes | P2 + P5 scenario |
| Colab topology (LLM + reranker + STT/TTS gateway) | P2; M1 in [10](./10-open-questions.md) |
| Decision trace schema writes (bootstrap) | P1 |
| Live append `decision_traces/` on accept/correct | P4 |
| Latency targets [05 §7](./05-models-and-runtime.md#7-latency-targets) | P2 measure; P5 load table |

---

## 8. Performance and observability (07) → phases

| Item | When |
|------|------|
| Composable tools / talk-first (no unrequested chains) | P1 design; enforced P5 |
| Rerank hops (RTT + batch) &lt;250 ms p95 target | P2 measure; P5 [07 §6](./07-performance-and-observability.md#6-load--acceptance-scenarios) |
| Gateway batching / connection reuse for decision hops | P2 |
| Staging cache (`root_id` + content hash) | P2+ |
| Recommendations refresh on graph commit only | P2 |
| Per-tool latency | P2+ |
| `tasks` / `custom` stream → dock progress | P2 |
| Root `jobs` ledger | P2 |
| LLM tokens per turn | P2 |
| Decision traces bootstrap + live | P1 bootstrap; P4 live |
| `interrupt` accept/reject analytics | P4 |
| `custom_fields` debug logging | P2 |
| LiveKit RTT / barge-in metrics | P2 |
| Placement eval gate | P1 |
| LLMTracer on extract until LangSmith/OTEL | P1 IntraDoc; review P4 |
| Logging dirs [07 §7](./07-performance-and-observability.md#7-logging-layout-proposed) | P1 bootstrap paths; P4 live traces |
| Load / acceptance scenarios (all rows) | P5 |

---

## Phase 0 — Specification

**Goal:** Single source of truth; implementers do not re-derive rules from v1.

- Sibling docs `00`–`11` + `references` aligned; workflows include P0/P1 and W2–W12.
- This file’s matrices updated when any spec section changes.
- Testing canon [11-testing.md](./11-testing.md): workflow matrix, CI stages, per-phase test exits.

**Exit:** [04](./04-agent-orchestration.md) tool list + agent table implementable without opening `v1` except optional reuse per [08](./08-migration-and-reuse.md); test layout and gates defined in [11](./11-testing.md).

---

## Phase 1 — Graph tools + decision bootstrap (reranker)

**Goal:** Headless graph API, **all** deterministic tools, agent harness without LiveKit, **gateway cross-encoder** `decision/score` before voice depends on routing.

### Graph & API

- Mongo schema per [03](./03-graph-and-memory.md) + [08 §2](./08-migration-and-reuse.md#2-committed-persistence).
- **REST:** graph CRUD + agent turn with shared `thread_id` [04 §10](./04-agent-orchestration.md#10-api-boundaries).
- **Projects API (P0 stub):** create empty project + Genesis shell for pytest (full UI in P2).
- Feature flag: v1 auto-reorg/link **off** for new projects [08 §8](./08-migration-and-reuse.md#8-feature-flags-transition).

### Agents (headless)

- Harness: Supervisor routes to Conversation, GistWorker, IntraDocWorker, LinkPlaceWorker, ReorgRecommend/ReorgApply, RetrievalWorker.
- IntraDocWorker: real or fixture LLM for extract tests; DecisionScorer **live gateway reranker** on integration path (`-m vllm`).
- Mock/score-only unit tests for tools; no LLM inside tools.

### Workflows (automated)

- [06](./06-workflows.md): **W2–W4, W7**, W3 commit path, W6 tools, W9 conversation-only, W11a highlight path.
- Explicit tests for **§11 anti-patterns** (e.g. gist question does not create ROOT).

### Decision (required exit)

- Parser: robotics notes → JSONL [05 §3](./05-models-and-runtime.md#3-decision-routing--cross-encoder-reranker), [08 §5](./08-migration-and-reuse.md#5-markdown-import-robotics--other-projects).
- Held-out **`query_node` + `frontier` → `label_relevance`** full vectors.
- Deploy gateway **`decision/score`** (cross-encoder; e.g. BGE reranker on CPU).
- Document eval metrics on held-out robotics labels via `eval_decision_model.py` [00 §9](./00-vision-and-principles.md#9-success-criteria-personal-research).

### Observability (partial)

- `backend/data/decision_training/` populated.
- Per-tool latency baseline; LLMTracer on extract path [07 §3](./07-performance-and-observability.md#3-instrumentation-required).

**Testing ([11 §7](./11-testing.md#7-phase-gates-testing)):** `tests/unit/tools/*` for every [04 §6](./04-agent-orchestration.md#6-deterministic-tools) tool; `tests/e2e/workflows` for W2–W4, W7, W3, W6, W9, W11a; `tests/e2e/anti_patterns`; integration agents (mock LLM); `-m vllm` gateway smoke (chat + `decision/score`) for Phase 1 exit.

**Exit:** Gist ROOT, deep-read commit, placement suggest, reorg preview via agents + **live reranker**; all [§5.2](#52-deterministic-tools-04-6) tools pass pytest; bootstrap eval documented; [11](./11-testing.md) Phase 1 gate green.

---

## Phase 2 — LangGraph + voice (full interactive stack)

**Goal:** Every workflow in [§4](#4-user-workflows-06--phases) voice/panel path; committed stack live [00 §8](./00-vision-and-principles.md#8-v2-platform-plan-committed).

### Runtime ([04 §12](./04-agent-orchestration.md#12-langgraph--langchain-runtime-interactive-agent); voice normative [§12.11–12.13](./04-agent-orchestration.md#1211-conversation-first-voice-normative))

**Phase 2 voice gate:** implementation must match **three-plane** voice (Conversation dialogue-only, WorkflowObserver + WorkflowAgent, async dispatch) per §12.11–12.13 before marking exit criteria green.

- Root StateGraph, checkpointer + `thread_id`, **`astream_events` v3** → dock + TTS.
- **`jobs`** ledger + `custom` stream for intra-doc/scorer progress.
- Foreground/background: context switch **parks** background work; HITL only for graph writes [04 §12.5](./04-agent-orchestration.md#125-context-switching-foreground-vs-background).
- `interrupt()` previews + `Command(resume=)` tied to dock approval ids.

### Voice & UI

- LiveKit: mute/unmute, barge-in, **custom fields**, project switcher.
- **P0/P1:** create project API in UI; first **unmute** → ProjectScopeWorker → `update_project_scope`.
- Recommendations dock: latest response, nudge classes, pending approvals [02 §4](./02-user-experience.md#4-recommendations-dock-default-not-optional).
- Canvas: unified graph, color by kind, structure-key layout [02 §5](./02-user-experience.md#5-knowledge-canvas--single-graph).
- Whisper base.en + edge-tts wired to same `thread_id` [05 §5](./05-models-and-runtime.md#5-speech-pipeline).

### Workflows (complete)

- All rows in [§4](#4-user-workflows-06--phases) marked P2 delivered, including **W3a/b/c**, **W5**, **W8**, **W11b**.

### Models

- LinkPlaceWorker, RetrievalWorker, ReorgRecommendWorker: **HttpDecisionScorer** (gateway reranker) required (no stub in prod).
- ContextPreprocessor injects scope when `introduction` set [04 §7](./04-agent-orchestration.md#7-project-lifecycle-create-vs-scope).

### Performance (initial)

- vLLM prefix cache; staging cache optional; recommendation list refresh rules [07 §5](./07-performance-and-observability.md#5-caching).

**Testing:** Full [11 §4](./11-testing.md#4-workflow-test-matrix-06) workflow e2e including P1, W8, W12; LiveKit `livekit` marker smoke; frontend dock/canvas tests ([11 §7](./11-testing.md#7-phase-gates-testing) Phase 2).

**Exit:** [00 §9](./00-vision-and-principles.md#9-success-criteria-personal-research) rows for voice, dock, placement, retrieval, deep read, catalog—**except** multi-project soak and full load table (P5); [11](./11-testing.md) Phase 2 gate green.

---

## Phase 3 — Markdown import to graph

**Goal:** Seed Mongo from three-tier notes; expand decision training beyond robotics exemplar.

- Import pipelines [08 §5](./08-migration-and-reuse.md#5-markdown-import-robotics--other-projects): `deeper_read_notes` → ROOT+gist; `select_papers` → intra-doc where applicable; `overall_insights` → hubs + insights + ROOT cites.
- Parallel refresh `decision_training/<project>/*.jsonl` [05 §8](./05-models-and-runtime.md#8-decision-trace-schema-training--eval).
- Optional fine-tune / per-project reranker [10 M2](./10-open-questions.md#3-models-and-runtime).
- Parser open items [10 M3](./10-open-questions.md#3-models-and-runtime).

**Exit:** Imported graph obeys [03](./03-graph-and-memory.md) tier rules; dataset size and eval documented per imported project.

---

## Phase 4 — Live traces, reranker refresh, polish

**Goal:** Continuous routing improvement + UX completeness without weakening HITL.

- Append **live** `decision_traces/` on user accept/correct (placement, retrieval expand, reorg choices) [05 §3.2](./05-models-and-runtime.md#32-delivery-order-v2--no-fine-tune-gate-for-p2p4).
- Optional reranker fine-tune cadence (manual or scripted).
- Complete [07 §3](./07-performance-and-observability.md#3-instrumentation-required) signals not yet wired: interrupt analytics, full token accounting review, OTEL/LangSmith where replacing LLMTracer.
- Canvas **color legend** polish; dock UX (done strip, tool trace expand) [02](./02-user-experience.md).
- Optional nudge impression logging; **`decision_traces`** for optional reranker training [03 §10](./03-graph-and-memory.md#10-nudges-vs-training-traces).

**Exit:** Live traces feeding retrain pipeline; suggestions remain **HITL** for all graph writes.

---

## Phase 5 — Hardening

**Goal:** Production confidence; v1 paths fenced; spec anti-patterns not regressible.

- Soak: multi-project switch, custom fields stress, deepen gist ROOT (W3b), long W2→W3a chains.
- Run all [07 §6](./07-performance-and-observability.md#6-load--acceptance-scenarios) acceptance scenarios.
- Monitor canvas structure-key thrash [07 §4](./07-performance-and-observability.md#4-frontend-graph-canvas).
- Remove or fence remaining v1 autonomous ingest/reorg/scrollback routes [01](./01-v1-baseline.md), [08 §4](./08-migration-and-reuse.md#4-replace--wrap).
- Re-run [06 §11](./06-workflows.md#11-anti-patterns-must-not-happen) checklist.

**Exit:** Load table green or documented exceptions; no v1 implicit ingest on new projects.

---

## 9. Explicitly not revived from v1

| v1 behavior | v2 stance | Verified in |
|-------------|-----------|-------------|
| Ingest URL → link + generalize + reorg | **Forbidden** | P1 flags; P5 fence |
| Global Master Chat scrollback as workspace | **Replaced** by recommendations dock | P2 |
| Auto `reorganize_overclustered_nodes` on ingest | **Forbidden**; ReorgRecommendWorker + approve only | P1–P2 |
| Implicit graph writes from summary chat | **Forbidden** | P1 tests; P2 UX |
| Generative JSON / chat-LLM decision hops | **Not shipped** — gateway reranker | P1 |
| Logprob-only / LoRA-on-Ministral decision | **Superseded** (2026-11-18) | — |
| Port v1 modules that contradict spec | **Skip** per [08](./08-migration-and-reuse.md) reuse doctrine | All phases |

---

## 10. Deferred (not v2 core)

- Full Lean / circuit-tracer engines (math/safety rubric only in MVP).
- Optional Drex/Laya comparison beyond eval curiosity.
- Canvas section hulls unless [10 U1](./10-open-questions.md#2-user-experience) closes toward them.
- Direct manipulation drag/context menu beyond MVP pin ([02 §5.5](./02-user-experience.md#55-direct-manipulation)).

---

## 11. Optional v1 reuse (08) — by phase

Reuse is **never required**. When useful and spec-aligned:

| Candidate ([08 §3](./08-migration-and-reuse.md#3-port-list-high-confidence)) | Phase |
|------------------------------------------------------------------------------|-------|
| Fetch/search, trafilatura, passage packing, extract prompts | P1 |
| `db.py` models → tool adapters | P1 |
| GraphCanvas, physics pipeline, structure key | P2 |
| graph analytics (features only) | P1–P2 DecisionScorer inputs |

**Do not port:** orchestrator monolith, graph_ingestion_engine auto paths, generative `subgraph_expansion` [08 §4](./08-migration-and-reuse.md#4-replace--wrap).

---

## 12. Open questions → phase gates

**Locked:** see [10 §6](./10-open-questions.md#6-resolved-decisions-locked) (A1–A3, A4, U1–U3, U5–U6, M1, M3–M4, P1, P3).

| ID | Status | Blocks or shapes |
|----|--------|------------------|
| **U4** | Open | Pinned vs freeform custom fields UX |
| **M2** | Open | Global vs per-project reranker checkpoint → P3/P4 |
| **P2** | Deferred | Non-robotics import importers |

Close remaining items in [10](./10-open-questions.md) → update this section and affected phase bullets.

---

## 13. Maintaining this document

When adding or changing any spec section:

1. Add or update a row in [§2](#2-master-coverage-matrix-spec--phase).
2. Map workflows in [§4](#4-user-workflows-06--phases) and tools in [§5](#5-agents-and-deterministic-tools--phases) if affected.
3. Adjust phase **Exit** bullets if success criteria shift.

**README** points here as the full rollout map—not a high-level summary only.

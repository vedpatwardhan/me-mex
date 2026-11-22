# Testing and CI

> **Canon:** [06-workflows.md](./06-workflows.md), [04-agent-orchestration.md](./04-agent-orchestration.md), [09-phasing.md](./09-phasing.md). **Goal:** Every **deterministic tool**, **worker agent**, **feature**, and **user workflow** has explicit **unit**, **integration**, and (where applicable) **end-to-end** coverage before a phase exit.

v1 pytest suites live on git tag **`v1`** only. On `main`, `backend/tests/{unit,integration,e2e}` target composable tools and workflows—no orchestrator monolith gates.

---

## 1. Test layers

| Layer | Scope | External deps | Runs in CI default? |
|-------|--------|---------------|---------------------|
| **Unit** | Single function/module: tools, guards, parsers, dock queue, checkpoint I/O, pure graph helpers | None (in-memory Mongo mock or `mongomock` / testcontainers opt-in) | **Yes — required** |
| **Integration** | Agent subgraph + real Mongo test DB + mocked LLM **or** fixture responses; DecisionScorer **live gateway reranker** on marked suite | MongoDB test instance; optional `vllm` marker | **Yes** (mocked LLM); **nightly / manual** (`pytest -m vllm`) for Colab |
| **End-to-end (API)** | REST `thread_id` full turns: supervisor → worker → tools → Mongo; no browser | Mongo + headless LangGraph | **Yes** |
| **End-to-end (product)** | Voice/UI: LiveKit, dock streams, canvas actions (W12), project switch | Local stack + optional Playwright | **Phase 2+**; CI smoke subset |

**Rule:** Deterministic **tools** must have **unit tests with no LLM mock inside the tool**—only the agent layer mocks or calls remote vLLM.

---

## 2. Repository layout (v2 target)

```
me-mex/
  backend/
    pytest.ini
    tests/
      conftest.py              # fixtures: db, project, thread_id, checkpoint tmp dir
      unit/
        tools/                 # one module per tool group (04 §6)
        graph/                 # immutable guards, edge rules, staging I/O
        bootstrap/               # notes → JSONL parser
        checkpoints/             # JSON round-trip
      integration/
        agents/                  # per worker: Conversation, Gist, IntraDoc, …
        decision/                # DecisionScorer + gateway (vllm marker)
        langgraph/               # interrupt/resume, jobs ledger, park/resume
      e2e/
        workflows/               # one file per 06 workflow (P0, P1, W2–W12)
        anti_patterns/           # 06 §11 — must fail if violated
      fixtures/
        graphs/                  # small seeded Mongo JSON
        llm/                     # recorded tool-call transcripts
  frontend/
    tests/                       # Vitest/RTL: dock, filters, canvas structure-key
  voice_worker/
    tests/                       # LiveKit voice worker smoke (Phase 2)
```

**Naming:** `test_<tool_name>.py`, `test_agent_<worker>.py`, `test_workflow_<id>.py` (e.g. `test_workflow_w2_gist_inquiry.py`).

---

## 3. Coverage requirements by artifact

### 3.1 Deterministic tools ([04 §6](./04-agent-orchestration.md#6-deterministic-tools))

**Unit (each tool, happy + guard paths):**

| Group | Minimum cases |
|-------|----------------|
| Gist & scratch | create/update ROOT, attach URI, note/todo, promote ToDo |
| Intra-doc | fetch text fixture; staging upsert/edit; commit under `root_id`; **no** LLM in tool |
| Link | ROOT↔INSIGHT only default; highlight; embedding query with fixed vector |
| Reorg | preview diff shape; apply plan; split/relocate; illegal immutable write → `ImmutableNodeViolation` |
| Project | `update_project_scope` |
| Dock | `enqueue_pending_approval`, `list_pending_approvals` ordering |

**Contract:** Calling a tool twice with same args → same Mongo state (idempotent where spec says so).

### 3.2 Worker agents ([04 §5.1](./04-agent-orchestration.md#51-worker-agents-model-work--tools))

**Integration (per agent):**

| Agent | Prove |
|-------|--------|
| **Supervisor** | Routes P1, W2, W3, W4, W5, W11 utterances to correct worker (table [04 §8](./04-agent-orchestration.md#8-supervisor-routing-intent--agent)) |
| **Conversation** | Summary/gist talk **no** ROOT without explicit persist |
| **GistWorker** | Direct explicit gist commit → ROOT; summary request → `gist_root` approval; approve → ROOT + optional source URI |
| Source gist | Short summary request with URL in any custom-field value → fetch exact source, brief completion acknowledgement, reviewable approval; no ROOT before approval |
| Voice routing resilience | Committed-scope acknowledgement stays Conversation-only; malformed Supervisor output falls back to Conversation while active jobs remain visible |
| **IntraDocWorker** | Extract (mock LLM) → staging → commit after interrupt approve |
| **LinkPlaceWorker** | DecisionScorer frontier keys = full vector; enqueue only; edges after approve |
| **ReorgRecommend / Apply** | Preview → apply; no v1 cascade |
| **RetrievalWorker** | BFS hop mock scorer; `highlight_nodes` |
| **ProjectScopeWorker** | Incomplete scope → no graph writes; complete → `update_project_scope` |
| Scope revision | ProjectScope structured output chooses incremental correction vs full replace; pending proposal is the baseline when present |

### 3.3 Features / UX contracts ([02](./02-user-experience.md))

| Feature | Test type |
|---------|-----------|
| Recommendations **initiate only** | E2E: tap nudge → preview, **no** Mongo until approve |
| `custom_fields` override STT | Unit: `context_preprocessor` (+ supervisor node via `route_intent`) |
| Dock job status from `jobs` + custom stream | Integration LangGraph |
| Canvas delete (W12) | E2E API + optional Playwright |
| Structure-key layout | Frontend unit: layout not called on selection-only |
| Scope visible in dock | Component/e2e Phase 2 |

### 3.4 Models ([05](./05-models-and-runtime.md))

| Component | Tests |
|-----------|--------|
| Bootstrap parser | Unit: robotics three files → JSONL rows; held-out split reproducible |
| DecisionScorer | Integration `-m vllm`: output keys = 100% frontier ids |
| Reranker eval | Script/test: ranking metric on held-out bootstrap (optional gate) [00 §9](./00-vision-and-principles.md) |
| Checkpoint JSON | Unit: save/load `thread_id`, resume after interrupt |

### 3.5 Voice three-plane ([04 §12.11–12.13](./04-agent-orchestration.md))

Marker **`voice_plane`** (default CI; HTTP/SSE only, no LiveKit room).

| Contract | Test module |
|----------|-------------|
| Conversation no tools on voice | `test_voice_conversation_stream.py` |
| Async dispatch off hot path | `test_voice_dispatch_enqueued.py` |
| Chit-chat skips worker | `test_voice_chit_chat_no_graph.py` |
| Briefing API | `test_session_briefing_api.py` |
| Worker reply not hot-path TTS | `test_streaming_voice_filter.py` |
| Background source gist is acknowledged, then becomes a brief follow-up plus Review/Approve ROOT proposal | `test_voice_source_gist_flow.py`, `test_session_plane_gist_followup.py` |
| WorkflowAgent metadata | `test_workflow_agent.py` |
| §12.13 surface | `test_voice_spec_invariants.py` |
| W9 voice path | `test_workflow_w9_voice_summary.py` |

---

## 4. Workflow test matrix ([06](./06-workflows.md))

Every workflow row **must** have at least one **e2e** test (REST Phase 1; + voice Phase 2). Anti-patterns **must** have dedicated tests that assert forbidden behavior does not occur.

| ID | E2E file (target) | Phase 1 (REST) | Phase 2 (+ voice/LiveKit) |
|----|-------------------|----------------|---------------------------|
| §0 | `test_recommendations_initiate_only.py` | Required | + dock tap |
| P0 | `test_workflow_p0_create_project.py` | Required | UI smoke |
| P1 | `test_workflow_p1_scope.py` | Mock multi-turn | LiveKit |
| W2 | `test_workflow_w2_gist_inquiry.py` | Required | Required |
| W3a/b/c | `test_workflow_w3_deep_read_*.py` | Required | Required |
| W4 | `test_workflow_w4_link.py` | Required | Required |
| W5 | `test_workflow_w5_reorg.py` | Required | Required |
| W6/W6b | `test_workflow_w6_note_todo.py` | Required | Optional voice |
| W7 | `test_workflow_w7_rich_commit.py` | Required | Required |
| W8 | `test_workflow_w8_muted_browsing.py` | N/A | Required |
| W9 | `test_workflow_w9_summary_only.py` | Required | Required |
| W11 | `test_workflow_w11_retrieval.py` | Required | Required |
| W12 | `test_workflow_w12_canvas_edit.py` | API delete + nudge | UI + nudge |
| §11 | `tests/e2e/anti_patterns/` | **Required suite** | Same |

---

## 5. Fixtures and markers

| Fixture | Purpose |
|---------|---------|
| `empty_project` | P0/P1 |
| `robotics_seed_graph` | W4/W5/W11 (small import or hand-built) |
| `tmpdir_checkpoint` | JSON checkpointer dir per test |
| `mock_vllm_chat` | Returns fixed assistant + tool calls |
| `recorded_intra_doc_chunks` | IntraDoc without live LLM |

**pytest markers** (extend `pytest.ini`):

| Marker | Meaning |
|--------|---------|
| `vllm` | Needs live Colab gateway (vLLM chat + `decision/score` reranker) |
| `mongodb` | Needs real Mongo (testcontainers or local `me_mex_test`) |
| `livekit` | Phase 2 worker + room |
| `slow` | Long intra-doc extract |

Default CI: `pytest -m "not vllm and not livekit and not slow"`.

---

## 6. CI pipeline (required)

| Stage | Command / action | Gate |
|-------|------------------|------|
| **Lint / typecheck** | ruff + mypy (or project standard) on `backend/`, `voice_worker/` | Required in CI |
| **Unit** | `pytest tests/unit` | Required in CI |
| **Integration** | `pytest tests/integration -m "not vllm"` | Required in CI |
| **E2E workflows** | `pytest tests/e2e/workflows tests/e2e/anti_patterns` | Required in CI |
| **Frontend** | `npm test` (dock + canvas utils) | Required in CI (Phase 2+) |
| **Decision eval** | `pytest tests/integration/decision -m vllm` or scripted eval | **Phase 1 exit** |
| **Nightly** | full `-m vllm` + optional Playwright | Non-blocking until stable |

Do **not** treat a phase as complete if any workflow in [§4](#4-workflow-test-matrix-06) lacks a passing test for that phase.

**Coverage:** Track line coverage on `app/tools/` and worker agents; **target ≥ 90%** on tools and guards; **100%** of tools listed in [04 §6](./04-agent-orchestration.md#6-deterministic-tools) must have at least one unit test file before Phase 1 exit.

---

## 7. Phase gates (testing)

| Phase | Testing exit |
|-------|----------------|
| **1** | All tools unit-tested; W2–W4, W7, W3 commit, W6, W9, W11a e2e REST; anti-pattern suite green; bootstrap reranker eval / gateway smoke; integration agents with mock LLM |
| **2** | All workflows e2e including P1, W8, W12; LiveKit smoke; dock stream assertions; frontend tests for dock/canvas |
| **3** | Import pipeline tests; imported graph obeys [03](./03-graph-and-memory.md) invariants |
| **4** | `decision_traces` append tests on accept/correct |
| **5** | [07 §6](./07-performance-and-observability.md#6-load--acceptance-scenarios) load tests; soak multi-project |

---

## 8. What v1 tests are not

Do **not** use passing v1 tests as proof of v2 behavior:

- Monolithic orchestrator / ingest throughput / auto-reorg cascade
- `subgraph_expansion` generative hops
- v1 domain pills / multi-edge-type assumptions

When porting a v1 test, **rewrite** against [06](./06-workflows.md) and [04 §6](./04-agent-orchestration.md#6-deterministic-tools) or delete.

---

## 9. Maintaining this document

When adding a tool, agent, or workflow in spec:

1. Add a row to [§4](#4-workflow-test-matrix-06) or [§3](#3-coverage-requirements-by-artifact).
2. Implement the test **in the same change** as the feature (or TDD first).
3. Update [09-phasing.md](./09-phasing.md) phase exit if gates change.

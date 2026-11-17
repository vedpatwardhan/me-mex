# Me-Mex (v2)

**Me-Mex** is a voice-first **external memory** for research: a MongoDB knowledge graph, LangGraph agents, and human-in-the-loop approvals—so you can gist papers, deep-read into concepts, link ROOTs to hubs, and reorganize topology **without** silent auto-ingest.

This repository is the **v2 rebuild**. The old monolithic chat/ingest stack lives on git tag **`v1`** (see [docs/01-v1-baseline.md](./docs/01-v1-baseline.md)).

---

## What v2 is (and is not)

| v2 | Not v2 (v1 / deferred) |
|----|-------------------------|
| **Workflow-driven** writes: conversation, recommendations, explicit approve | URL paste → ingest + link + reorg in one shot |
| **Deterministic tools** touch Mongo; agents call LLM / DecisionScorer only | Tools that call the model inside `app/tools/*` |
| **ROOT** gists, **staging → commit** intra-doc, **LoRA** placement/retrieval | Global master chat scrollback as the workspace |
| **Phase 1 today:** headless REST + pytest (`/api/v2/*`) | LiveKit voice, dock UI, streaming canvas (Phase 2+) |

Full product and engineering canon lives in **[`docs/`](./docs/)** — start at [docs/README.md](./docs/README.md) and [docs/00-vision-and-principles.md](./docs/00-vision-and-principles.md).

**Rollout & test gates:** [docs/09-phasing.md](./docs/09-phasing.md) · [docs/11-testing.md](./docs/11-testing.md) · [docs/06-workflows.md](./docs/06-workflows.md)

---

## Implementation status

| Phase | Focus | In this repo |
|-------|--------|----------------|
| **1** | v2 schema, deterministic tools, LangGraph harness, mock DecisionScorer, bootstrap JSONL + Colab runbook | **Backend** under `backend/app/v2/`; default `uv run pytest` |
| **2+** | LiveKit, React dock, `astream_events`, full voice UX | `frontend/` exists but is **not** the v2 target UI yet |

---

## Prerequisites

- **Python 3.11+** and **[uv](https://docs.astral.sh/uv/)**
- **MongoDB** on `localhost:27017` (databases `me-mex` dev, `test-me-mex` for tests)
- Optional: Colab **vLLM + LoRA** for `-m vllm` tests ([colab/RUNBOOK.md](./colab/RUNBOOK.md)) — not required for default CI

---

## Quick start (backend)

```bash
cd me-mex
uv sync
```

Copy or edit `backend/.env` (see `backend/.env.test` for test DB name). Minimum for v2:

```env
ME_MEX_V2=1
MONGO_URI=mongodb://localhost:27017
DB_NAME=me-mex
```

Run API:

```bash
uv run uvicorn main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload
```

Run tests (v2 suite; v1 tests quarantined under `backend/tests/v1_legacy/`):

```bash
uv run pytest
```

Create a project and agent turn (examples):

```bash
curl -X POST 'http://localhost:8000/api/v2/projects?name=Demo'
curl -X POST http://localhost:8000/api/v2/agent/turn \
  -H 'Content-Type: application/json' \
  -d '{"text":"hello","thread_id":"t1","context_json":{"active_project_id":"<project_id>"}}'
```

---

## Repository layout

```
me-mex/
  docs/              # v2 product & engineering spec (source of truth)
  backend/
    app/v2/          # models, tools, agents, /api/v2 routes
    app/             # v1 modules (still mounted when v2 flag off)
    tests/           # unit / integration / e2e (v2 default path)
    data/            # checkpoints, decision_training fixtures
  frontend/          # v1-era UI (Phase 2+ redesign per docs/02)
  colab/             # LoRA train/deploy runbook (user-executed)
  pyproject.toml     # uv dependencies + pytest config
```

---

## API surfaces

| Surface | When | Purpose |
|---------|------|---------|
| **`/api/v2/*`** | `ME_MEX_V2=1` | Projects, graph helpers, `agent/turn`, `agent/resume` — Phase 1 harness |
| **`/api/chat`** | Legacy | v1 orchestrator; fenced over time ([docs/09-phasing.md](./docs/09-phasing.md) Phase 5) |

Details: [docs/04-agent-orchestration.md](./docs/04-agent-orchestration.md).

---

## Decision model & robotics bootstrap

Notes → JSONL for LoRA training: [docs/05-models-and-runtime.md](./docs/05-models-and-runtime.md), `backend/app/v2/bootstrap/`, `backend/data/decision_training/`. Training runs on **Colab** (not in default pytest). Eval stub:

```bash
uv run python backend/scripts/eval_decision_model.py --dry-run
```

Exemplar markdown for parsers lives in the parent cortex-os repo (`docs/deeper_read_notes.md`, etc.) — see [docs/references.md](./docs/references.md).

---

## Contributing / reading order

1. [docs/00-vision-and-principles.md](./docs/00-vision-and-principles.md) — why and success criteria  
2. [docs/06-workflows.md](./docs/06-workflows.md) — what users do (P0, W2–W12, anti-patterns)  
3. [docs/04-agent-orchestration.md](./docs/04-agent-orchestration.md) — agents, tools, routing  
4. [docs/09-phasing.md](./docs/09-phasing.md) — what to build when  
5. Implement against [docs/11-testing.md](./docs/11-testing.md) gates  

For v1 archaeology: `git checkout v1` and [docs/01-v1-baseline.md](./docs/01-v1-baseline.md).
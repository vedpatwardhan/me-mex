# Me-Mex (v2)

**Me-Mex** is a voice-first **external memory** for research: a MongoDB knowledge graph, LangGraph agents, and human-in-the-loop approvals—so you can gist papers, deep-read into concepts, link ROOTs to hubs, and reorganize topology **without** silent auto-ingest.

The monolithic v1 stack (orchestrator ingest, `/api/chat`) is preserved only on git tag **`v1`** — see [docs/01-v1-baseline.md](./docs/01-v1-baseline.md).

---

## What this repo is (and is not)

| In scope on `main` | Not on `main` |
|--------------------|---------------|
| Workflow-driven writes + explicit approve | URL → auto ingest + link + reorg |
| Deterministic tools + LangGraph workers | v1 `ExecutiveOrchestrator` |
| Headless REST + pytest (`/api/*`) | LiveKit dock UI (Phase 2+) |
| Agents call `get_chains().invoke` / `get_decision_scorer()` (stub in CI) | **LoRA train + deploy on Colab** (`pytest -m vllm` for exit gate) |

Canon: **[`docs/`](./docs/)** — [docs/README.md](./docs/README.md), [docs/09-phasing.md](./docs/09-phasing.md), [docs/11-testing.md](./docs/11-testing.md).

---

## Prerequisites

- **Python 3.11+**, **[uv](https://docs.astral.sh/uv/)**
- **MongoDB** on `localhost:27017` (`me-mex` dev, `test-me-mex` tests)

---

## Quick start

```bash
cd me-mex
uv sync
```

`backend/.env` (see `backend/.env.example`):

```env
MONGO_URI=mongodb://localhost:27017
DB_NAME=me-mex
```

```bash
uv run uvicorn main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload
uv run pytest   # default excludes -m vllm (see backend/pytest.ini)
# Bootstrap decision JSONL (Colab LoRA prep):
cd backend && uv run python -m app.bootstrap.notes_to_jsonl
cd backend && uv run python -m app.bootstrap.split_train_eval data/decision_training/robotics/bootstrap.jsonl --out-dir data/decision_training/robotics
```

Example:

```bash
curl -X POST 'http://localhost:8000/api/projects?name=Demo'
curl -X POST http://localhost:8000/api/agent/turn \
  -H 'Content-Type: application/json' \
  -d '{"text":"hello","thread_id":"t1","context_json":{"active_project_id":"<project_id>"}}'
```

---

## Layout

```
me-mex/
  docs/                 # product & engineering spec
  backend/
    app/
      agents/           # LangGraph supervisor + workers
      tools/            # deterministic graph tools + search_tools
      db/               # Store / Mongo
      api/              # FastAPI routes
      bootstrap/        # notes → JSONL
      services/         # llm_gateway, decision_scorer, checkpoints, …
    tests/              # unit, integration, e2e
  frontend/             # legacy UI until Phase 2
  colab/
```

---

## API

All agent and graph endpoints live under **`/api/*`** (`/api/projects`, `/api/agent/turn`, `/api/agent/resume`, …). Details: [docs/04-agent-orchestration.md](./docs/04-agent-orchestration.md).

---

## Decision bootstrap

[docs/05-models-and-runtime.md](./docs/05-models-and-runtime.md), `app/bootstrap/`, `backend/data/decision_training/README.md`, [colab/RUNBOOK.md](./colab/RUNBOOK.md), [colab/TOPOLOGY.md](./colab/TOPOLOGY.md), [colab/me_mex_inference_stack.ipynb](./colab/me_mex_inference_stack.ipynb).

```bash
uv run python backend/scripts/eval_decision_model.py --dry-run
```
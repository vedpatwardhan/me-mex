# Me-Mex v2 — Product & Engineering Spec

This folder is the **source of truth** for the rebuild after git tag **`v1`**. **Start here:** [00-vision-and-principles.md](./00-vision-and-principles.md).

---

## 1. How to read this spec

| Doc | Purpose |
|-----|---------|
| [00-vision-and-principles.md](./00-vision-and-principles.md) | **Canon** — workflow, platform plan, principles, success criteria |
| [01-v1-baseline.md](./01-v1-baseline.md) | What `v1` shipped; gaps vs markdown workflow |
| [02-user-experience.md](./02-user-experience.md) | Voice rail, default recommendations dock, unified color-coded graph |
| [03-graph-and-memory.md](./03-graph-and-memory.md) | Three tiers, MongoDB model, ROOT-only insights, staging |
| [04-agent-orchestration.md](./04-agent-orchestration.md) | LangGraph runtime (streaming, interrupts, jobs), agents + deterministic tools |
| [05-models-and-runtime.md](./05-models-and-runtime.md) | Colab gateway — Ministral, cross-encoder reranker, Whisper, Kokoro; notes bootstrap for eval |
| [06-workflows.md](./06-workflows.md) | End-to-end user workflows and anti-patterns |
| [07-performance-and-observability.md](./07-performance-and-observability.md) | Latency, tracing, decision datasets |
| [08-migration-and-reuse.md](./08-migration-and-reuse.md) | Optional v1 reuse (spec wins) + markdown import |
| [09-phasing.md](./09-phasing.md) | **Full rollout map** — phases + coverage matrices (spec → delivery) |
| [10-open-questions.md](./10-open-questions.md) | Unresolved decisions only |
| [11-testing.md](./11-testing.md) | Unit / integration / e2e matrix, CI, phase test gates |
| [references.md](./references.md) | Repo and exemplar pointers |

---

## 2. Relationship to other documents

| Location | Role |
|----------|------|
| [`../README.md`](../README.md) | Repo entrypoint — quick start, layout, links here |
| `git checkout v1` | Reference autonomous codebase ([01-v1-baseline.md](./01-v1-baseline.md)) |
| `docs/me-mex/*` (cortex-os repo) | Historical rebuild notes (non-canon) |
| `docs/deeper_read_notes.md` etc. (cortex-os) | Robotics tier **exemplar** for bootstrap JSONL / Phase 3 import |

---

## 3. Spec status

| Area | Status |
|------|--------|
| Vision & platform | **Aligned** — [00](./00-vision-and-principles.md) |
| Graph, agents, UX, workflows | **Aligned** — no `domain_mode`; P0/P1 scope onboarding |
| Phase 1 backend | **Done on `main`** — headless `/api/*`, tools, tests; decision canon = **gateway reranker** (spec 2026-11-18); Phase 2 = voice + dock |
| Voice / dock / canvas | **Phase 2 in progress** — LiveKit + dock stream on `main`; exit gate [11 §7](./11-testing.md) |

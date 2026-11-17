# Performance and observability

> **Canon:** [00-vision-and-principles.md](./00-vision-and-principles.md) §7–8. **Models:** [05-models-and-runtime.md](./05-models-and-runtime.md).

v2 improves latency by **not running v1 ingest bundles**, using **decision hops** instead of generative BFS, and scoping heavy LLM to **tools you invoke**. Observability feeds **LoRA training** and your tuning—not black-box agent runs.

---

## 1. v1 bottlenecks (why it felt slow)

From `docs/reports/` and `backend/logs/llm_traces/`:

| Bottleneck | When it hit |
|------------|-------------|
| **`subgraph_expansion`** (generative per hop) | Retrieval and ingest traversal |
| **Collective linking + generalization** | After ingest |
| **`reorganize_overclustered_nodes`** | Post-ingest cascade (v2: **replaced** by decision-model reorg **recommendations**) |
| **Conversation summary refresh** | Many chat turns |

v2 **does not** remove intra-doc extract cost when you deep-read; it removes **unrequested** link/reorg/traverse chains.

---

## 2. v2 performance strategy

| Lever | Effect |
|-------|--------|
| **Composable tools** | Gist-only paths avoid extract entirely |
| **LoRA DecisionScorer** | Sub-250 ms target per hop vs multi-second LLM expand |
| **vLLM prefix cache** | Shared graph prefix across option scoring |
| **Staging cache** | Re-open staging without re-extract unchanged text |
| **Talk-first** | Inquiry + summary without Mongo or tool latency |
| **HITL** | No surprise long jobs writing graph in background |

---

## 3. Instrumentation (required)

| Signal | Use |
|--------|-----|
| Per-tool latency | Dev tuning; UX “Thinking” honesty |
| LangGraph **`tasks` / `custom` stream** | Job progress in dock (intra-doc chunks, scorer hops) |
| Root state **`jobs`** ledger | “What’s the status of X?” without re-querying Mongo |
| LLM tokens per turn | Colab budget |
| **Decision traces** (hop + placement) | LoRA dataset live + bootstrap |
| `interrupt` accept/reject | HITL analytics |
| `custom_fields` presence | Debug STT vs typed conflicts |
| LiveKit RTT / barge-in cancel rate | Voice UX |
| Placement eval (held-out) | LoRA adapter quality gate ([05](./05-models-and-runtime.md) §3) |

Retain v1 **`LLMTracer`** on extract/consolidation paths until LangSmith/OTEL covers them.

---

## 4. Frontend graph (canvas)

Per [02-user-experience.md](./02-user-experience.md) §5.4 — inherit v1 **stabilized** force graph:

- Layout work on **structure key** change (load, ingest commit, delete), not selection/hover/SSE highlight.
- Monitor: unexpected layout thrash (structure key churn without graph mutation) is a regression.

---

## 5. Caching

- **vLLM:** prefix cache for decision option batches.
- **Staging:** keyed by `root_id` + content hash.
- **Recommendations:** refresh on graph commit, not every utterance.

---

## 6. Load / acceptance scenarios

| Scenario | Success signal |
|----------|----------------|
| ~80-node project, bounded retrieval hops | p95 hop <250 ms (**LoRA** decision) |
| Voice barge-in during `merge_mutable_nodes` | Run cancelled; no partial corrupt write |
| Large PDF → intra-doc staging ready | Time to **staging preview** only—no link/reorg timer |
| 10 gist commits in one session | No extract/reorg invocations unless requested |
| Robotics bootstrap eval | LoRA ranking on held-out **query + frontier** batches ([05 §8](./05-models-and-runtime.md), [00 §9](./00-vision-and-principles.md)) |

---

## 7. Logging layout (proposed)

```
backend/logs/
  llm_traces/          # extract/consolidation (v1-style, tool-scoped)
  decision_traces/     # live decision hops
backend/data/
  decision_training/   # bootstrap JSONL per project
  checkpoints/         # LangGraph session state — plain JSON per thread_id (not Mongo)
```
# Performance and observability

> **Models:** [05-models-and-runtime.md](./05-models-and-runtime.md). **Agents:** [04-agent-orchestration.md](./04-agent-orchestration.md).

v2 improves latency by **not running v1 ingest bundles**, using **reranker decision hops** instead of generative BFS, and scoping heavy LLM to **work you invoke**. Observability feeds **eval / optional reranker training** and your tuning—not black-box agent runs.

---

## 1. v1 latency problems (why v2 differs)

| v1 pattern | Issue |
|------------|-------|
| **`subgraph_expansion`** (LLM text per hop) | Multi-second retrieval |
| **Monolithic ingest orchestrator** | Long blocking bundles |
| **`reorganize_overclustered_nodes`** | Post-ingest cascade (v2: **replaced** by decision-model reorg **recommendations**) |

---

## 2. v2 latency strategy

| Mechanism | Effect |
|-----------|--------|
| **Composable tools** | Only pay for paths you route |
| **Cross-encoder DecisionScorer** | One batched rerank per hop vs multi-second LLM expand |
| **Multi-hop retrieval** | Several HTTP `decision/score` calls—budget **RTT + rerank** per hop |
| **Intra-doc LLM** | Only on **IntraDocWorker**, not every turn |

---

## 3. Instrumentation required

| Signal | Use |
|--------|-----|
| Tool call latency (per tool name) | Regression on deterministic paths |
| **Decision hop latency** | RTT + gateway rerank batch |
| LLMTracer / token usage (extract) | Cost and slow prompts |
| **Decision traces** (hop + placement) | Eval dataset live + bootstrap |
| `jobs` ledger + LangGraph `custom` stream | Dock progress |
| Checkpointer write size / frequency | Thread health |

| Eval | Gate |
|------|------|
| Placement eval (held-out) | Bootstrap reranker quality ([05](./05-models-and-runtime.md) §3) — optional threshold |

---

## 4. Frontend graph canvas

Structure-key layout from v1—minimize ReactFlow thrash when recommendations update ([02 §5.4](./02-user-experience.md#54-layout-and-rendering-performance-carry-forward-from-v1)).

---

## 5. Caching

| Layer | Notes |
|-------|-------|
| Staging read cache (intra-doc) | Optional repeated passage reads |
| **vLLM** prefix cache | Chat / tool prompts—not used for decision reranker |
| Recommendation dock | Debounce list refresh on stream events |
| Gateway | Reuse HTTP client; warm reranker model once at gateway startup |

---

## 6. Load / acceptance scenarios

| Scenario | Target |
|----------|--------|
| ~80-node project, bounded retrieval hops | p95 hop **&lt;250 ms** (**RTT + rerank**); depth × hops stacks |
| Voice turn | TTFA per [05 §7](./05-models-and-runtime.md#7-latency-targets) |
| Intra-doc extract | Progress visible; no silent 5+ min block without `jobs` |
| Robotics bootstrap eval | Reranker ranking on held-out **query + frontier** batches ([05 §8](./05-models-and-runtime.md), [00 §9](./00-vision-and-principles.md)) |

---

## 7. Log layout (local)

```
backend/logs/
  decision_traces/     # live decision hops
backend/data/
  decision_training/   # bootstrap JSONL per project
```
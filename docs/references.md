# References

> Pointers for implementers. **Product canon** is `me-mex/docs/`, led by [00-vision-and-principles.md](./00-vision-and-principles.md).

---

## 1. me-mex repository

| Path | Description |
|------|-------------|
| [`README.md`](../README.md) | v2 entrypoint (quick start, layout) |
| **`docs/`** (this folder) | v2 product & engineering canon |
| `assets/101126.png`, `assets/101126_2.png` | v1 graph screenshots (historical) |
| Git tag **`v1`** | v1 code + old `docs/ARCHITECTURE.md`, `ROADMAP.md`, `RESEARCH_SYNTHESIS.md` |

---

## 2. Robotics workflow exemplar (cortex-os)

Acceptance fixtures for tier shape and decision bootstrap:

| Path | Tier |
|------|------|
| [`docs/deeper_read_notes.md`](../../docs/deeper_read_notes.md) | Catalog |
| [`docs/select_papers.md`](../../docs/select_papers.md) | Deep read |
| [`docs/overall_insights.md`](../../docs/overall_insights.md) | Cross-paper insights |

Other projects replicate this pattern in isolated workspaces.

---

## 3. Rebuild research (cortex-os `docs/me-mex/`)

| Path | Description |
|------|-------------|
| `memex_rebuild_prompt.md` | Original rebuild brief |
| `memex_rebuild_feasibility_and_plan.md` | Deep research plan—**corrected** in spec (see [10-open-questions.md](./10-open-questions.md)) |
| `curated_links_digest.md` | Curated links notes |
| `relevant_daily_papers.md`, `nov_daily_papers.md` | Paper lists |

---

## 4. External integration references

| Topic | Pointer |
|-------|---------|
| [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) | HITL, `Command(resume=)` |
| [LangGraph checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers) | `thread_id`, durability |
| [LangGraph streaming / event streaming v3](https://docs.langchain.com/oss/python/langgraph/event-streaming) | Dock + TTS + task status |
| [LangGraph Send / Command](https://docs.langchain.com/oss/python/langgraph/graph-api-send-command) | Parallel intra-doc, state updates |
| [LangChain `create_agent`](https://reference.langchain.com/python/langchain/agents/create_agent) | Worker subgraphs |
| LiveKit agents | LiveKit documentation |
| `dqbd/langgraph-livekit-agents` | LangGraph + LiveKit patterns |
| ToolSpace (arXiv:2611.05036) | Workflows graph inspiration |
| WikiTrace / EvoMemState | Evidence-linked memory patterns |
| Ministral 3 8B on vLLM | Mistral / Hugging Face recipes |

---

## 5. Spec index

Full document map: [README.md](./README.md).
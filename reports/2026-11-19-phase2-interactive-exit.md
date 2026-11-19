# Phase 2 interactive exit report — 2026-11-19

**Branch:** `main`  
**Baseline:** voice E2E working (2026-11-18); this batch completes dock↔voice, HITL over LiveKit, job park MVP, and CI gate.

---

## 1. Executive summary

Phase 2 **interactive MVP exit** for personal research use: voice session stays connected while the **recommendations dock** mirrors backend SSE via LiveKit data channel; **approve/dismiss** works over voice or REST; **foreground park** marks background intradoc jobs paused on new turns; P1/W8/barge-in/canvas delete hooks landed. Automated **79 pytest** paths green (default + `vllm` + `livekit` token) with MongoDB; frontend vitest **4** tests green.

**Explicitly not claimed:** full 04 §12.5 LangGraph subgraph park, Playwright voice e2e for every workflow row, P5 multi-project soak.

---

## 2. Deliverables

### Voice + dock (M1)

- [`frontend/src/utils/dockStreamReducer.ts`](../frontend/src/utils/dockStreamReducer.ts) — pure reducer for `token`, `approval`, `custom`/`job`, `turn_end`, `dock_events`
- [`useDockState`](../frontend/src/hooks/useDockState.ts) — `applyStreamEvent`, voice session ref for HITL
- [`voiceSession.ts`](../frontend/src/services/voiceSession.ts) — `DataReceived` for dock payloads; `sendAgentTurn` (W8)
- [`worker.py`](../agent/me_mex_agent/worker.py) — incremental `dock_event` + `turn_start` during SSE
- [`turn_bridge.py`](../agent/me_mex_agent/turn_bridge.py) — `on_chunk` callback
- [`App.tsx`](../frontend/src/App.tsx) — wires VoiceRail ↔ dock

### HITL over voice (M2)

- Dock **Approve/Dismiss** → `VoiceSession.sendApproval` when room connected
- Worker **`approve`/`cancel`** data → `post_resume` → dock `turn_end` + optional TTS

### Job park (M3)

- [`job_runtime.py`](../backend/app/agents/job_runtime.py) — thread background intradoc, `park_active_jobs`
- [`graph.py`](../backend/app/agents/graph.py) — park yield on `astream_agent_turn`; optional bg when `background_intradoc=1` or `INTRADOC_BG_SLEEP_S`
- [`workers.py`](../backend/app/agents/workers.py) — `force_project_scope`, `resume_job_id` routing

### UX (M4–M5)

- **P1:** `force_project_scope` on first unmute when introduction empty
- **W8:** muted turn button; worker allows intent-only turns
- **Barge-in:** `cancel_tts` / `cancel_turn` on unmute and new turn
- **Project switch:** republish LiveKit context on project/selection change
- **W12:** `RightDrawer` in App; delete refreshes dock nudges
- **Jobs:** amber job rows in RecommendationsDock

### Bug fix (exit gate)

- [`store.py`](../backend/app/db/store.py) `create_project` — genesis via `upsert_node` so `project_ids` matches `list_nodes` (P0 graph API)

---

## 3. Exit test matrix (2026-11-19)

| Command | Result |
|---------|--------|
| `uv run pytest -m "not vllm and not livekit and not slow"` | **76 passed** |
| `TESTING=1 DECISION_SCORER_MODE=live pytest tests/integration/decision -m vllm -n 0` | **1 passed** (live Colab reranker) |
| `uv run pytest -m livekit -n 0` | **2 passed** (token API + agent mint) |
| `cd frontend && npm test -- --run` | **4 passed** |
| Colab `GET /health`, `POST /tts/synthesize` (manual) | **200** (session with tunnel) |

**Prerequisites:** MongoDB `localhost:27017`, optional Colab tunnel in local `backend/.env` (not committed).

---

## 4. Manual smoke (recommended)

```bash
./scripts/dev-stack.sh start
```

1. **Start voice session** → speak → dock shows streaming reply.  
2. **Mute mic** (do not End session) → hear TTS.  
3. Trigger approval → **Approve** in dock → stay connected.  
4. **Muted turn** with `intent=` in custom fields.  
5. Select node → RightDrawer → delete → graph + dock refresh.

---

## 5. Remaining (Phase 3+ / polish)

- LiveKit **room-level** pytest (join + data round-trip)
- Workflow matrix automated **voice** variants beyond `test_voice_bridge_workflow.py`
- Deeper LangGraph **checkpoint park** for long IntraDoc (04 §12.5 full)
- Colab notebook §2 (ffmpeg, `COLAB_INFERENCE_BASE_URL`) hygiene if using notebook bring-up
- Multi-project soak → Phase 5

---

## 6. Commit context

This report accompanies commit **Phase 2 interactive stack: dock-voice, HITL, job park** on `main`. Prior voice VAD commit: `36985b8`.

See also: [2026-11-18-phase2-voice-progress.md](./2026-11-18-phase2-voice-progress.md).

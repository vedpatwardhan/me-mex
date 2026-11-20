# Demo runbook — workflow smoke (any research domain)

> **Purpose:** Manual checklist to confirm Me-Mex v2 **workflows** work for **your** demo topic—not robotics graph seeding. Robotics notes in the repo are **routing/eval fixtures** only ([00 §2.5](./00-vision-and-principles.md#25-reference-artifacts-robotics-exemplar)).
>
> **Spec mapping:** workflows [06](./06-workflows.md); UX [02](./02-user-experience.md); automated gates [11](./11-testing.md).

**Time:** ~45–75 minutes for the **core** path (§4–§8). Optional deep-read/link/reorg (§9) adds 20–40+ minutes (Colab LLM).

---

## 1. What “pass” means

| Principle | You should observe |
|-----------|-------------------|
| **No silent ingest** | Casual Q&A (W9) does **not** add `ROOT` nodes without an explicit commit/approve. |
| **HITL** | Graph writes show in the **recommendations dock** with **Approve** / **Dismiss** (or you used an explicit “create ROOT…” command). |
| **Voice session** | **Mute mic** keeps LiveKit connected; **End session** only when fully done. |
| **Your domain** | Project scope and paper URLs reflect **your** research—not pre-loaded robotics markdown. |

Keep a simple log: step id → **PASS** / **FAIL** / **SKIP** + one line of notes.

---

## 2. Prerequisites

### 2.1 Services

| Check | Command / action |
|-------|------------------|
| MongoDB | `mongosh --quiet mongodb://localhost:27017 --eval 'db.runCommand({ ping: 1 })'` → `ok: 1` |
| Colab stack | Tunnel up per [colab/RUNBOOK.md](../colab/RUNBOOK.md); `curl -sS "$COLAB_INFERENCE_BASE_URL/health"` → 200 |
| Local env | `backend/.env`: `MONGO_URI`, `DB_NAME`, `COLAB_INFERENCE_BASE_URL`, `CHAT_LLM_MODE=live`, `LIVEKIT_*` |
| Agent env | `agent/.env` (or inherited): `ME_MEX_BACKEND_URL=http://127.0.0.1:8000`, same Colab URL |

Do **not** commit real tunnel URLs.

### 2.2 Optional automated gate (before UI)

From `me-mex/`:

```bash
uv run pytest -m "not vllm and not livekit and not slow"
uv run pytest -m livekit -n 0
# If Colab is up:
cd backend && TESTING=1 DECISION_SCORER_MODE=live uv run pytest tests/integration/decision -m vllm -n 0
```

### 2.3 Bring up UI stack

**Terminal A** (foreground; Ctrl+C stops all):

```bash
cd me-mex
./scripts/dev-stack.sh start
```

**Terminal B** — Colab tmux stack if not already running.

Open **http://127.0.0.1:3000** (or the port `dev-stack` prints). Logs: `.dev-stack/logs/backend.log`, `agent.log`, `frontend.log`.

### 2.4 Demo inputs (prepare once)

Pick **one** public source you are comfortable citing in the demo (not robotics-specific), e.g.:

- An arXiv abstract URL, or  
- A stable blog / report URL you know well.

You will paste the id or URL into **Custom fields** on the voice rail (`key=value` lines).

Example custom fields block (edit for your source):

```text
arxiv_id=
source_url=https://arxiv.org/abs/XXXX.XXXXX
root_id=
intent=
```

### 2.5 Observability during demo (Phase 4)

Tail while you walk §4–§8:

```bash
tail -f me-mex/.dev-stack/logs/backend.log me-mex/.dev-stack/logs/agent.log
```

| Signal | Where to look |
|--------|----------------|
| Voice conversation plane | `backend.log`: `conversation_stream thread_id=` · `voice_dispatch job_id=` |
| Background jobs | `backend.log`: `job_start` · `job_status` |
| Reranker hops | `backend.log`: `decision_hop_ms=` · `scenario=placement\|reorg_neighbor\|retrieval_expand` |
| HITL approve/dismiss | `backend.log`: `hitl action=` |
| Agent voice path | `agent.log`: `voice_turn thread_id=` · `VAD utterance` · `STT utterance` |
| Live decision dataset | `backend/logs/decision_traces/<project_id>/<date>.jsonl` (append on scorer + placement/reorg approve) |
| Extract / slow LLM | `backend/logs/llm_traces/` |

Quick greps (another terminal):

```bash
rg 'conversation_stream|voice_dispatch|decision_hop_ms|hitl action|job_status' me-mex/.dev-stack/logs/backend.log
rg 'voice_turn|STT utterance|voice_turn failed' me-mex/.dev-stack/logs/agent.log
```

Set `DECISION_TRACE_ENABLED=false` in `backend/.env` to skip JSONL append during a noisy session.

**2 min smoke** (optional, before §4): run a placement or reorg flow through dock **Approve**; confirm a new line under `backend/logs/decision_traces/<project_id>/` and `hitl action=approve` in `backend.log`. Then proceed with the full Phase 2 script (§4–§8) using the tails/greps above.

---

## 3. Pre-flight (2 min)

| # | Action | Expected | ✓ |
|---|--------|----------|---|
| 3.1 | `curl -sS http://127.0.0.1:8000/api/livekit/token -X POST -H 'Content-Type: application/json' -d '{"room":"me-mex","identity":"demo"}'` | JSON with `token` | |
| 3.2 | Open UI; confirm canvas + voice rail + recommendations dock visible | No console hard errors | |
| 3.3 | Tail `agent.log` in another pane | No repeating stack traces | |

---

## 4. Core demo script

Use a **fresh project** name like `Demo — <your topic>` so the graph stays easy to reset later (delete project via API or new project tab).

### Step A — P0 Create project (UI only)

| # | Action | Expected | ✓ |
|---|--------|----------|---|
| A1 | Navbar → **Create project** (or **+**); name + short description (can be empty) | New tab appears; canvas shows **Genesis** (or empty project shell) | |
| A2 | Switch to the new project tab | Voice rail shows new `project_id` | |

**Workflow:** [06 P0](./06-workflows.md#p0--create-project-ui-only-no-agent-tool)

---

### Step B — P1 Project scope (first voice)

| # | Action | Expected | ✓ |
|---|--------|----------|---|
| B1 | **Start voice session** | Status moves past `Connecting…`; LiveKit connected | |
| B2 | **Unmute mic** (new project has no scope) | Hint: “Unmute to set project scope (P1)” may show; dock streams assistant | |
| B3 | Say what the project is about in **your** words (field, goals, source types)—2–3 short answers if the agent asks follow-ups | Conversation only; **no** new paper `ROOT`s yet | |
| B4 | Confirm when agent summarizes scope | Scope text appears in dock; Genesis/description updates after approve if prompted | |
| B5 | **Mute mic** while assistant finishes / TTS plays | Session **stays** connected (`mic off (session active)`); hear TTS without re-connecting | |

**Logs:** `agent.log` → `STT utterance`, `voice_turn reply_len=…` (no `voice_turn failed`); `backend.log` → `POST /api/voice/conversation/stream` (conversation-first) and optional `dispatch job_id=…`; proactive TTS may log after job `done` / `awaiting_approval` — no trailing ASGI `ERROR`.

**Workflow:** [06 P1](./06-workflows.md#p1--first-voice-project-scope-before-research)

---

### Step C — W9 Inquiry / summary (no graph write)

| # | Action | Expected | ✓ |
|---|--------|----------|---|
| C1 | Set `source_url=` (or `arxiv_id=`) in custom fields; **Unmute** | Fields published on context update | |
| C2 | Ask: *“Summarize this paper in a few sentences—don’t save anything to the graph yet.”* | Streaming reply in dock; **node count unchanged** (no new `ROOT`) | |
| C3 | Ask a follow-up factual question about the same source | Still conversation-only | |

**Anti-pattern check:** [06 W9](./06-workflows.md#9-w9--summary-only-no-graph); compare with `backend/tests/e2e/anti_patterns/test_no_implicit_root.py` behavior.

---

### Step D — W2 Gist thread → optional ROOT commit

| # | Action | Expected | ✓ |
|---|--------|----------|---|
| D1 | *“What’s the gist? What is the main contribution?”* (same URL in fields) | Gist prose in dock; still **no** `ROOT` unless you commit | |
| D2a | **Recommended path:** wait for dock nudge *create ROOT* → review preview → **Approve** | New gist-colored `ROOT` on canvas; edge from Genesis (if wired) | |
| D2b | **Fast path (demo):** add `force_gist_commit=true` to custom fields, say *“Create ROOT titled \<short title\>; gist is \<one sentence\>.”* | `ROOT` appears after turn completes (may still show approval depending on worker) | |

Note `root_id` in custom fields after commit for later steps.

**Workflow:** [06 W2](./06-workflows.md#2-w2--gist-inquiry-no-root-yet)

---

### Step E — W6 Note or ToDo

| # | Action | Expected | ✓ |
|---|--------|----------|---|
| E1 | *“Create a todo: read section 3 of this paper by Friday.”* | Dock shows proposal or confirmation; **ToDo** node (or approval then node) | |
| E2 | Optional: *“Add a short note on my open questions.”* | Note node or staging text | |

**Workflow:** [06 W6](./06-workflows.md#6-w6--capture-note--todo)

---

### Step F — W11a Retrieval + highlight

| # | Action | Expected | ✓ |
|---|--------|----------|---|
| F1 | Click your new `ROOT` on canvas (selection → `selected_node_ids`) | Right drawer opens | |
| F2 | *“What in this project relates to \<keyword from your scope\>?”* | Short answer; canvas **highlight** on some nodes (transient) | |
| F3 | Confirm highlight clears or updates on next question | No unsolicited graph writes | |

**Requires:** Colab `POST /v1/decision/score` healthy (gateway reranker).

**Workflow:** [06 W11a](./06-workflows.md#w11a--you-ask-primary)

---

### Step G — W8 Muted browsing + custom-field turn

| # | Action | Expected | ✓ |
|---|--------|----------|---|
| G1 | **Mute mic**; pan/zoom canvas; change selection | No uplink; agent silent | |
| G2 | Set `intent=` or edit fields; click **Send muted turn (custom fields)** | Dock shows a turn driven by fields (no STT) | |
| G3 | **Unmute** when ready | Back to `Listening` | |

**Workflow:** [06 W8](./06-workflows.md#8-w8--muted-browsing)

---

### Step H — HITL Approve / Dismiss (voice path)

Pick any **pending approval** from earlier steps, or trigger a small write that needs approve:

| # | Action | Expected | ✓ |
|---|--------|----------|---|
| H1 | With voice session active, dock shows **Approve** on a pending item | Voice state may show `Awaiting approval` | |
| H2 | Click **Approve** (mic can stay **muted**) | Turn resumes; item clears; graph reflects write | |
| H3 | Optional: trigger another approval and **Dismiss** | No graph change for dismissed id | |

**Workflow:** [02 §4.2](./02-user-experience.md#42-recommendations-below-latest-response--nudges-and-approvals)

---

### Step I — W12 Canvas delete

| # | Action | Expected | ✓ |
|---|--------|----------|---|
| I1 | Select a **non-Genesis** node you created (e.g. a note); Right drawer → delete → confirm | Node removed; canvas refreshes | |
| I2 | Check dock | Optional nudge (reconnect/reorg)—**initiate only**, no auto-write | |

**Workflow:** [06 W12](./06-workflows.md#11-w12--manual-graph-edits-canvas)

---

### Step J — Clean shutdown

| # | Action | Expected | ✓ |
|---|--------|----------|---|
| J1 | **End session** on voice rail | Disconnected; can start again later | |
| J2 | Ctrl+C in `dev-stack` terminal | Processes stop cleanly | |

---

## 5. Optional extensions (if demo needs write-heavy paths)

Only run if Colab **chat** (`/v1/chat/completions`) is stable—these are slow.

| Step | Workflow | Voice / UI hint | Pass signal |
|------|----------|-----------------|-------------|
| **K** | W3c Deep read | `source_url=` + *“Deep read this—show concepts before commit.”* | Staging list in dock → edit → approve commit under `ROOT` |
| **L** | W4 Link | Select `ROOT` + hub/insight if any; *“Where should this connect?”* | Placement candidates → approve edges |
| **M** | W5 Reorg | After several nodes: *“This section is crowded—suggest a split.”* | Preview diff → approve apply |

Set `root_id=<id>` in custom fields for W3b instead of W3c if you already have a gist `ROOT`.

---

## 6. REST fallback (if voice is blocked)

Use the same `thread_id` pattern as the UI (`voice-<project_id>`) or any string.

```bash
PROJECT_ID="<from UI or POST /api/projects>"
curl -sS -X POST http://127.0.0.1:8000/api/agent/turn \
  -H 'Content-Type: application/json' \
  -d "{\"text\":\"Summarize only—no graph writes.\",\"thread_id\":\"demo-rest\",\"context_json\":{\"active_project_id\":\"$PROJECT_ID\"}}"
```

Streaming (closer to dock):

```bash
curl -N -X POST http://127.0.0.1:8000/api/agent/turn/stream \
  -H 'Content-Type: application/json' \
  -d "{\"text\":\"Hello\",\"thread_id\":\"demo-rest\",\"context_json\":{\"active_project_id\":\"$PROJECT_ID\"}}"
```

If REST works but voice fails, focus debugging on LiveKit + `agent.log` before blocking on workflow logic.

---

## 7. Troubleshooting quick map

| Symptom | Likely cause | Where to look |
|---------|--------------|---------------|
| No STT / empty utterance | Colab speech or VAD / mute too early | `agent.log` (`VAD utterance ready … flush=silence\|mute`), Colab `speech.log`; speak then pause ~0.5 s or mute after ≥0.4 s speech |
| Dock never streams | Worker ↔ backend SSE | `agent.log` (`turn_bridge`), `backend.log` |
| Rerank / retrieval errors | Gateway `decision/score` | `gateway.log`; run `-m vllm` test |
| Token / join failure | LiveKit Docker | `docker ps`; `LIVEKIT_*` in `backend/.env` |
| TTS cuts off | Barge-in on unmute | Mute during playback (by design) |
| Wrong project graph | Tab not switched | Navbar project tab + voice rail `Project:` line |

---

## 8. Results summary (fill after run)

**Date:** __________  
**Project name:** __________  
**Colab tunnel:** up / down  
**Commit:** `git rev-parse --short HEAD`

| Section | Result | Notes |
|---------|--------|-------|
| 3 Pre-flight | | |
| A P0 | | |
| B P1 | | |
| C W9 | | |
| D W2 | | |
| E W6 | | |
| F W11 | | |
| G W8 | | |
| H HITL | | |
| I W12 | | |
| K–M optional | | |

**Blockers for next engineering work:** (list FAIL items only)

---

## 9. After a green run

You have validated **workflow + voice + HITL** for a general research project. Reasonable next engineering tracks (see `reports/HANDOFF_2.md` §9):

1. **Phase 2 harden:** LiveKit room smoke pytest; expand `agent/tests/test_voice_bridge_workflow.py` for any §8 FAIL rows.
2. **Skip:** Bulk markdown import (Phase 3)—deferred; grow the graph via voice/workflows only.
3. **Phase 4 remainder:** canvas legend, dock done-strip / tool trace UI when the demo narrative is stable ([09 §Phase 4](./09-phasing.md#phase-4--live-traces-reranker-refresh-polish)).

---

*Operational companion:* [../README.md](../README.md) local dev stack, [11-testing.md](./11-testing.md) CI gates.

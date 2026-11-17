# User experience

> **Canon:** [00-vision-and-principles.md](./00-vision-and-principles.md) §6–8. **Canvas nodes / edges:** [03-graph-and-memory.md](./03-graph-and-memory.md) §4–6 (kinds detailed in §5). **Agent payload:** [04-agent-orchestration.md](./04-agent-orchestration.md).

The UI supports **voice-first research** with a **single knowledge graph** (v1-style force graph, not separate tier views), a **voice rail**, and a **default right dock** for the latest reply plus recommendations. **Custom fields** carry exact values STT cannot reliably capture.

---

## 1. Summary

| Area | v2 behavior |
|------|-------------|
| Voice | **LiveKit** mute/unmute; Whisper-tiny STT; Kokoro TTS |
| Canvas | **One graph** per project; **color + label** by node kind (gist ROOT, deep ROOT, immutable concepts, mutable knowledge, insight, note, **ToDo**) |
| Right dock | **Always on** — latest turn + **recommendations** (nudges, **job status**, pending **write** approvals) |
| Precision | **Custom fields** on voice rail every turn |
| Memory | **Canvas** = [03 §5](./03-graph-and-memory.md#5-canvas-node-kinds) node kinds + uniform edges; **passages** off-canvas ([03 §4](./03-graph-and-memory.md#4-canvas-vs-database)); **no** full-height chat scrollback |

**Invariants:** No implicit ingest from conversation; graph writes via explicit tools only.

---

## 2. Layout

```
┌──────────┬────────────────────────────────────┬─────────────────────┐
│ Voice    │     Knowledge canvas               │ Recommendations     │
│ rail     │  (single graph, colors, highlights)  │ dock (default)      │
│          │                                    │ • latest response   │
│ Mute     │                                    │ • next actions      │
│ Custom   │                                    │                     │
│ fields   │                                    │                     │
│ Project  │                                    │                     │
└──────────┴────────────────────────────────────┴─────────────────────┘
        ▲                                          ▲
        │                                          │
     LiveKit                         Streaming reply + workflow nudges
```

There is **no** separate catalog / depth / insights **view mode**. Tiers from markdown still exist in the **data model**; you read them through **node colors**, labels, and filters—not by swapping the whole canvas.

---

## 3. Voice rail

| Control | Purpose |
|---------|---------|
| **Mute / unmute** | Session stays up; muted = no uplink audio |
| **Custom fields** | Key/value (arxiv id, metrics, node ids) → `context_json.custom_fields` **every turn** |
| **Pin fields** | Keep values across turns (optional—[10-open-questions.md](./10-open-questions.md)) |
| **Push-to-talk** | Optional hotkey |
| **State** | `Muted | Listening | Thinking | Speaking | Awaiting approval` |
| **Create project** | Top bar — **API only** (not an agent tool); then optional “unmute to begin” ([06 P0–P1](./06-workflows.md)) |
| **Project switcher** | `active_project_id` in payload—**same LiveKit room**; switch project in UI (no room-per-project) |
| **Custom fields + voice** | Transcript + fields every turn—fields hold exact URLs/ids (see [10 U3](./10-open-questions.md#6-resolved-decisions-locked)) |
| **Paste / fields** | URL / arXiv / local path via **custom fields** (not STT-only) |

**New project:** After **Create project** (API), UI may prompt **unmute**. Scope onboarding (**P1**) starts on **first unmute** with empty scope—not on button click alone.

**Project scope in dock:** Show current **introduction / scope** text (read-only block or chip) so you see what Mongo stores; edits via P1-style conversation or settings.

Preprocessor: **`custom_fields` authoritative** over conflicting STT in `text`.

---

## 4. Recommendations dock (default, not optional)

The **right dock is always visible** and is the **single control surface** for conversation, **everything you might approve**, and proactive nudges—so you are not juggling a giant chat log, hidden modals, and the graph.

### 4.1 Latest response (top of dock)

- **Current turn** text: your utterance (or STT partial while speaking) + **streaming assistant reply**.
- **Worker badge** when a subgraph runs (from LangGraph **`tasks`** / **`subgraphs`** stream); **progress** lines from **`custom`** stream (e.g. intra-doc chunk 4/12).
- **Job status:** in-flight work the user asked for appears in dock as a **status chip** or row tied to `job_id` (backed by root graph `jobs` state—[04 §12.4](./04-agent-orchestration.md#124-tracking-what-the-user-asked-for-job-ledger)).
- **Inquiry-first:** prose in this block does **not** imply graph writes until you **approve** a recommendation or give an explicit persist command.
- **Topic thread:** short multi-turn context on one source stays in session memory; dock shows **latest** exchange prominently (not project-wide scrollback).
- Optional: expand tool trace for the active turn.

This replaces v1 **Global Master Chat**; it is **not** a second optional widget.

### 4.2 Recommendations (below latest response) — nudges **and** approvals

One **ordered list** (ranked). **Tap/voice starts a step** (context + options)—**nothing auto-executes** a graph write ([06 §0](./06-workflows.md#0-how-recommendations-work-all-workflows)).

| Class | Examples | What tap does |
|-------|-----------|----------------|
| **Nudge / start** | “Create ROOT with this gist”, “Deep-read this paper?”, “Connect here?”, “Reorganize crowded hub” | Opens **guided** flow: show gist preview, staging, placement scores, or reorg plan—you decide next |
| **Pending approval** | Final commit after you’ve refined | **Approve** / **Edit** / **Dismiss** → Mongo write |
| **Informational** | “This relates to ToDo X” | No write; optional follow-up |

**Pending approval** items appear only when a **graph write** needs your OK (after extract completes, placement candidates, reorg diff, etc.)—via `enqueue_pending_approval` and/or LangGraph **`interrupt()`** preview. **Context switches** (you talk about something else while intra-doc runs) do **not** create approval rows; see **job status** chips and [04 §12.5](./04-agent-orchestration.md#125-context-switching-foreground-vs-background).

| Approval type | When it appears | What you see in the dock |
|---------------|-----------------|-------------------------|
| **Create ROOT (gist)** | After W2 gist thread stabilizes | Proposed `ROOT` title + gist from conversation—or skip if you used direct command |
| **Intra-doc staging** | After **IntraDocWorker** extract (e.g. right after deep-read generation) | Staging concept list; inline rename/drop/split; **Commit intra-doc graph** action |
| **Intra-doc commit** | `commit_intra_doc_graph` `interrupt` | Final preview of `CONCEPT_I` + passage refs under `ROOT` |
| **Placement** | After **LinkPlaceWorker** scoring | Ranked link candidates; approve one or more **`ROOT` ↔ hub/insight** edges |
| **Reorg apply** | After `preview_reorg_diff` | Before/after topology summary |
| **Destructive / bulk** | Delete, archive, large `update_project_scope`, merge | Diff + explicit confirm |
| **Scope / onboarding** | Proposed project intro from **P1** thread | Scope text preview → `update_project_scope` |

**Canvas coupling:** Selecting a recommendation **may** highlight affected nodes on the graph; the **approve/edit UI stays in the dock**.

### 4.3 Voice and state

- **Approve / reject / edit** via voice maps to the **same recommendation ids** as tap targets (`approve` / `cancel` tokens on LiveKit data channel per [04-agent-orchestration.md](./04-agent-orchestration.md)).
- Voice rail state **`Awaiting approval`** when the list has one or more **pending approval** items (optional badge count).
- List **refreshes** after commits, dismissals, and project switch; completed items drop off or move to a short “done this session” strip (implementation detail).

---

## 5. Knowledge canvas — single graph

### 5.1 One graph, typed nodes

- **Same interaction model as v1:** pan/zoom force (or similar) layout; entire project graph visible (with search/filters as needed).
- **No** hard switch between “catalog view”, “depth view”, and “insights view”.
- **Selection** → `selected_node_ids` in `context_json`.
- **Retrieval** → transient **highlight** mask on existing nodes (not a separate graph).

### 5.2 Color and label legend (v2)

Colors are **fixed per node kind** so gist roots, deep-read sources, evidence, and your synthesis are scannable at a glance. Exact hex values are implementation detail; **roles** are spec:

| Visual role | Node kind | Meaning |
|-------------|-----------|---------|
| **ROOT (gist only)** | `ROOT`, no children `CONCEPT_I` | Catalog entry: title + gist only (`deeper_read_notes`) |
| **ROOT (with concepts)** | `ROOT` + intra-doc subgraph | Deep-read source (`select_papers` under that source) |
| **Immutable concept** | `CONCEPT_I` under a ROOT | Extracted evidence leaf; **distinct color** from ROOT |
| **Mutable knowledge** | `CONCEPT_M` (user hub) | Knowledge **you** structure—v1-style **mutable** hub/bridge |
| **Insight** | `INSIGHT` | Mutable takeaway you **ask** to store—**same** edit/CRUD path as `NOTE`, different color/label |
| **Note** | `NOTE` | Short capture from conversation or panel |
| **ToDo** | `TODO` | Open item; distinct color/badge; promotable to **`CONCEPT_M`** |
| **Genesis anchor** | `CONCEPT_M` | Project spine hub—**not** a separate canvas species (optional stronger border in UI) |

**Insight vs note:** **Only** `node_kind` + styling. Neither is a “document layer”; both are mutable nodes you commit explicitly. Markdown `overall_insights` bullets map to **`INSIGHT`** nodes when you import or save them—not to a special graph subtype.

**Passages:** Never rendered as nodes or edges; agent may load them for verification (`open_passages`) while you keep looking at **`ROOT`** / **`CONCEPT_I`** on the canvas.

**ROOT states:** Both gist-only and deep-read ROOTs show a **gist** on the node; **color** tells you whether intra-doc concepts exist underneath.

### 5.3 Filters (optional, not separate graphs)

- Toggle visibility: show/hide `CONCEPT_I`, notes, ToDos, etc. (**kind filters**—not separate catalog/insights **views**).
- Search by title/gist (v1-style canvas search).
- Filters **subset** the same graph—they do **not** replace the unified canvas.

### 5.4 Layout and rendering performance (carry forward from v1)

The canvas must **not** re-run full force-layout or expensive pre-layout on every interaction (selection, hover, highlight, dock updates, or minor store churn).

**v1 pattern to preserve** (`frontend/src/components/GraphCanvas.tsx`):

- **Structure key** — Recompute positions only when **topology** changes (nodes/edges added/removed), not when labels/colors/metadata update alone.
- **Prewarm + pin** — `prewarmForceSimulation` produces stable `(x, y, fx, fy)` before paint; positions live in a **persistent map**.
- **Incremental layout** — New nodes only when the graph grows; avoid global relayout on small edits when possible.
- **ForceGraph2D** — `cooldownTicks={0}` (or equivalent) so the d3 engine does **not** keep reheating on each frame after initial settle; redraw canvas from **pinned** coordinates.
- **Traversal/highlight** — Retrieval glow and selection change **paint only**; they do not re-trigger layout.

Goal: graph **draws once** (per structural load); pan/zoom and highlights are cheap; **re-layout** only on explicit graph commits or project switch—not on “node moved around” in the sense of UI state.

### 5.5 Direct manipulation

**Required (not voice-only):** delete **nodes** and **edges** from the canvas; select; pin/drag nodes (v1-style `fx`/`fy` when supported). REST/graph API applies destructive edits immediately for explicit UI actions.

**Agent-assisted** link/reconnect after edits goes through **recommendations + voice** ([06 W12](./06-workflows.md#11-w12--manual-graph-edits-canvas))—not silent auto-wiring.

Layout: same engine and performance rules as v1 (**§5.4**); evolve **`react-force-graph-2d`**. Hull overlays: deferred.

---

## 6. Request payload

```json
{
  "text": "…spoken or typed utterance…",
  "context_json": {
    "selected_node_ids": ["…"],
    "active_project_id": "…",
    "viewport_bounds": null,
    "constraints": {},
    "custom_fields": {
      "arxiv_id": "2510.12693",
      "reported_f1": "0.476",
      "root_id": "…"
    }
  }
}
```

LiveKit data or REST; same LangGraph `thread_id`.

### JSON context drawer (advanced)

Raw `context_json` edit; syncs with voice rail **custom fields**.

---

## 7. Product invariants (UX)

- **No** full-height scrollback chat as workspace
- **No** implicit ingest from dock/canvas interaction alone
- **No** autonomous overnight graph mutation UI
- Dock **always** shows latest response + recommendations; **graph-write HITL** appears as approval items; **background job** progress via `jobs` / custom stream (not approval)

---

## 8. Committed stack

| Layer | Choice |
|-------|--------|
| Voice transport | **LiveKit** |
| STT | **Whisper-tiny** |
| TTS | **Kokoro** |
| LLM | **Ministral 3 8B** on Colab **vLLM** |

**Agents local;** LLM/LoRA on Colab vLLM. STT/TTS default local—[10 M1](./10-open-questions.md#6-resolved-decisions-locked), [05 §6](./05-models-and-runtime.md#6-runtime-topology-local-agents--colab-models).
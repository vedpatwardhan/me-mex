# User workflows

> **Canon:** [00-vision-and-principles.md](./00-vision-and-principles.md) §6. **Agents & tools:** [04-agent-orchestration.md](./04-agent-orchestration.md). **Dock UX:** [02-user-experience.md](./02-user-experience.md) §4.

This document is the **end-to-end user journey**—what you do in the UI, when voice starts, and how **recommendations** relate to agent work. **Nothing in the dock auto-runs a graph write.**

---

## 0. How recommendations work (all workflows)

| Rule | Meaning |
|------|---------|
| **Initiate, not execute** | Tapping/voicing a recommendation **starts a guided step**: show context, options, drafts—**you** decide the next move. |
| **Conversation first** | On voice, **Conversation** speaks first (interim ack); workers fetch/score/extract **async** ([04 §12.11](./04-agent-orchestration.md#1211-conversation-first-voice-normative)). Gist, deep-read **content**, placement, and reorg can be discussed in dock **before** Mongo write. |
| **Approval = write** | ROOT creation, links, intra-doc commit, reorg apply happen only after you **approve** (button or voice). |
| **Direct path OK** | You can skip recommendations with an explicit command + `custom_fields` (e.g. arXiv id + “create ROOT; gist is …”). |

**Retrieval** is usually **on demand** (you ask); the only common **retrieval-related recommendation** is “this discussion relates to ToDo X” ([§10](#10-w11--retrieval)).

**Voice example (deep read):** You say *“build the intra-doc graph for this paper.”* Conversation replies *“I’ll start a deep read—you can keep talking.”* LangGraph dispatches **IntraDocWorker** async; dock shows a **job chip**; when staging is ready, **WorkflowAgent** adds an approval card and Conversation speaks a **short proactive line** ([04 §12.12](./04-agent-orchestration.md#1212-proactive-updates-blend-in)).

---

## 1. Modes (reference)

| Mode | Graph write? | Typical path |
|------|--------------|--------------|
| Inquiry / gist talk | No until approval | Conversation + background GistWorker; completed gist appears as a reviewable `gist_root` approval |
| Scope onboarding | Yes (project fields only) | Conversation → `update_project_scope` when agent satisfied |
| Gist ROOT commit | Yes | Recommendation or “create ROOT with gist …” |
| Deep read | Yes (after approve) | Three entry paths → extract → review → commit |
| Link / connect | Yes (after approve) | Recommendation or “connect A to B” |
| Reorg | Yes (after approve) | Recommendation or “split / move …” |
| Retrieval | No* | You ask; DecisionScorer BFS + highlight |
| Canvas delete/disconnect | Yes (UI) + optional agent | Immediate UI API; nudges for reconnect/reorg |

\*Unless you then link or save.

---

## P0 — Create project (UI only, no agent tool)

1. You click **Create project** (top bar or project switcher)—**REST/API** creates empty project record + Genesis shell in Mongo.
2. **No** LangGraph tool, **no** voice required for this step.
3. UI may show a short gap: e.g. “Unmute when you’re ready to set up this project.”
4. LiveKit session may attach on project switch; uplink audio stays **muted** until you choose.

---

## P1 — First voice: project scope (before research)

**Trigger:** New project has **empty** `introduction` / scope; you **unmute** (or equivalent “start talking”).

1. Agent (voice + dock): *“What is this project about?”*
2. **Multi-turn conversation**—agent asks follow-ups until its **scope-complete** criteria are met ([04 §7](./04-agent-orchestration.md)):
   - **What** you are working on  
   - **Where** it sits (field, lab, application)  
   - **Why** / goals  
   - **What kind of sources** you expect (e.g. robotics papers, blogs, mixed)—broad **exploration paradigm**
3. Until satisfied, agent **keeps clarifying**—no gist / intra-doc / link / reorg **writes** (inquiry OK).
4. When satisfied, agent summarizes scope; you confirm → **`update_project_scope`** (project record + Genesis description).
5. After commit, acknowledging the completed scope or asking what comes next stays in Conversation. Only an actual scope edit/restart creates another proposal.

Revisit scope later via conversation + `update_project_scope` or settings ([02](./02-user-experience.md)).

---

## 2. W2 — Gist inquiry (no ROOT yet)

**Example:** You provide a paper/article link in a custom field—under any field name—and ask for a short summary, brief overview, main idea, or gist.

1. Supervisor routes to **GistWorker**; the worker resolves the supplied source reference from the message and custom-field values, fetches that document, and creates a concise summary from its extracted text.
2. The dispatch turn streams a **Conversation** interim line (`utterance_intent=dispatch_interim`) that acknowledges the gist job and points to the dock—without describing source content or reading URL fields from custom fields. While the job runs, you can keep talking; normal Conversation uses only project scope and completed worker results, and a failed Supervisor classification falls back to Conversation-only.
3. On completion, the full gist appears in a **Review / Approve** dock item as a `gist_root` proposal. A **Conversation** proactive follow-up (`gist_followup`) points to the dock; it does not repeat the summary.
4. The proposal does **not** create a `ROOT` until you approve it. Approval calls **`create_or_update_root_gist`** and attaches the supplied source URI when available. A direct explicit create-ROOT request remains supported.

**Detailed analysis is W3, not W2:** *“Analyze this paper in detail,” “deep read,”* or requests for concept extraction route to IntraDocWorker, which stages concepts for review and approval.

**Direct commit path:** arXiv in fields + *“Create ROOT titled X; gist is …”* → GistWorker writes Mongo only because you explicitly asked it to.

---

## 3. W3 — Deep read (three entry paths)

All paths: extract **shows content first**; you choose what to include; **`commit_intra_doc_graph`** only after approval.

### W3a — Recommended after long paper thread

1. After extended W2 conversation on one source, dock may recommend: *“Deep-read this paper?”*
2. Tap/voice **starts** IntraDocWorker: fetch → LLM extract → staging in dock.
3. You edit concepts; approve commit under new or existing **`ROOT`**.

### W3b — Existing gist ROOT on canvas

1. Select **`ROOT`** (or `custom_fields.root_id`).
2. *“Deep read this paper”* / *“Build intra-doc graph.”*
3. Same staging → review → commit **under that `root_id`**.

### W3c — Direct deep read (URL + command)

1. arXiv in fields + *“Give me a deep read”* / *“Build concept graph for this URL.”*
2. Agent returns proposed concepts in dock; you say *“Include X, Y; drop Z.”*
3. Approve commit when ready.

**Never** auto-link to hubs or reorg on commit.

---

## 4. W4 — Connect / link nodes

**DecisionScorer:** `query_node` + `frontier` of placement targets → full relevance vector; agent explains options; **you** pick.

### W4a — Recommendation after new node

When a **`ROOT`** or other node is added, dock may recommend: *“Connect here?”* with ranked targets (hubs, `INSIGHT`, neighbors).

1. Tap recommendation → see **where it might fit** + scores.
2. You: *“Connect to hub A and B”* or pick in UI.
3. Approve → **`create_root_insight_edges`** (or general link tools).

### W4b — Manual (agent may not have suggested it)

1. *“Link this node to that hub”* with selection in `context_json`.
2. Agent may still run DecisionScorer to **show** options; you name targets; approve → write edges.

---

## 5. W5 — Reorganization

**Trigger (recommendation):** e.g. mutable hub **degree** grows after new links—dock: *“This hub is crowded—reorganize?”*

1. Tap → **ReorgRecommendWorker**: proposed sub-concepts, where nodes might move (DecisionScorer on frontiers).
2. You refine: *“Move this here, change this description, keep that.”*
3. **`preview_reorg_diff`** in dock → final approve → **`apply_reorg_plan`**.

**Manual:** *“Split this section …”* — same explain → refine → approve pattern.

---

## 6. W6 — Capture note / ToDo

Voice or explicit command → `create_note` / `create_todo`; optional link suggestions as **recommendations** only.

**W6b:** ToDo → **`promote_todo_to_concept_m`** when you pick the work back up.

---

## 7. W7 — Rich commit after thread

Multi-turn on one source → explicit *“Create ROOT + concepts; wire …”* with approval on non-trivial diffs.

---

## 8. W8 — Muted browsing

Mute: canvas, selection, **custom fields**—no agent speech. Unmute to resume voice workflows.

---

## 9. W9 — Summary only (no graph)

Link + *“Summarize”* → dock text only; may feed into W2 gist thread without creating `ROOT`.

---

## 10. W11 — Retrieval

### W11a — You ask (primary)

1. *“What relates to X?”* / question while nodes selected. **Seed:** **Genesis** by default; or `query_node_id` / canvas selection when set.
2. **RetrievalWorker:** bounded BFS from seed, **DecisionScorer** (gateway reranker) each hop (`query_node`, full frontier probs) → **top‑k** expand → **`highlight_nodes`** + short answer in dock.
3. **No** recommendation required.

### W11b — ToDo relevance (optional recommendation)

During a new discussion, agent may compare thread to open **ToDo** nodes → dock: *“This relates to ToDo Y”*—informational; does not auto-complete ToDo.

---

## 11. W12 — Manual graph edits (canvas)

When you **delete or disconnect** via the UI (not voice):

1. **Deterministic graph API** applies the delete/remove-edge immediately for your explicit UI action—**no** agent auto-approval.
2. Session/agent observes the delta (orphaned node, detached `ROOT`, hub degree drop, etc.).
3. **Recommendations dock** may nudge—**initiate only** ([§0](./06-workflows.md#0-how-recommendations-work-all-workflows)):
   - *“Reconnect this node?”* → LinkPlaceWorker + DecisionScorer when a node lost expected links.
   - *“This hub is sparse / crowded now—reorganize?”* → W5 path when degree crosses heuristics.
4. You respond via voice, recommendation tap, or further canvas edits; **graph writes from nudges** still HITL.

**Connect** new targets after manual edit: use **voice**, **recommendation-guided** placement, or selection in `context_json`—not silent auto-link from delete alone.

---

## 12. Anti-patterns (must not happen)

| Anti-pattern | Why forbidden |
|--------------|----------------|
| Create project via agent tool | **UI/API only** (P0) |
| Scope saved before agent criteria met (unless user forces) | **P1** quality |
| Gist question → auto `ROOT` | **W2** inquiry-first |
| Recommendation tap → silent Mongo write | **§0** initiate only |
| Summary → full v1 ingest + link + reorg | **Implicit ingest** |
| URL paste → automatic insights parent | User must **link** |
| Placement edges to `CONCEPT_I` by default | **ROOT-only** insights rule |
| Auto-commit intra-doc + link + reorg bundle | **Composable** steps |

---

## 13. Ordered journey (cheat sheet)

| Step | You | Agent / system |
|------|-----|----------------|
| P0 | Create project button | API only |
| P1 | Unmute → talk scope | Q&A until what/where/why/paradigm → `update_project_scope` |
| W2 | arXiv + “what’s the gist?” | Gist in dock; optional **create ROOT** recommendation |
| W3 | Deep read (3 paths) | Staging → your edits → commit |
| W4 / W5 | Link or reorg | Options in dock → you choose → approve |
| W11 | Ask or accept ToDo nudge | Highlight / relate; no auto-write |
| W12 | Delete node/edge on canvas | Immediate UI write; optional reconnect/reorg nudges |

Legacy numbering in [00 §6.2](./00-vision-and-principles.md) maps to **P1 → W2 → W3 → …** above.

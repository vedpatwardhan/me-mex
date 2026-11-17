# Me-Mex v2 — Vision & principles

> **Status:** Product & engineering canon (`me-mex/docs/`). Tagged codebase baseline: git tag `v1`.  
> **Scope:** Product vision and design principles. Implementation detail lives in sibling spec documents (see [§10](#10-related-specification)).

Me-Mex v2 is a **personal research memory system**: a knowledge graph plus a voice-capable agent that helps you do the same work you already do in markdown—faster, with less scrolling, and with **you** deciding what gets stored and how it connects.

---

## 1. Summary

Each week you process large volumes of literature. You maintain **three layers of notes** (catalog → deep read → cross-paper synthesis). Me-Mex maps those layers onto a **per-project graph**, assisted by an agent that can answer questions, propose structure, and run tools—but **only writes to the graph when you ask**.

The robotics notes in the cortex-os `docs/` folder are the **reference example** of this workflow. The same pattern applies to **other projects** (different PIs, different literatures) in **isolated workspaces**—each project’s **scope comes from a short onboarding conversation**, not from a fixed “domain” toggle.

---

## 2. How research is done today

### 2.1 Catalog — `deeper_read_notes.md`

- You skim **hundreds of papers** over time.
- Each entry gets a **short gist**: title or id plus roughly **two–three lines** on what the paper does.
- **Every catalogued paper still shows up in `overall_insights`** (cited in synthesis bullets). What varies is **whether you deep-read it**—not whether it belongs in the cross-paper layer.

### 2.2 Deep read — `select_papers.md`

- For **important** papers you write **longer, ordered bullet lists**: concepts, mechanisms, and takeaways in the sequence you care about.
- This is manual, high-effort synthesis tied to that paper only.

### 2.3 Cross-paper insights — `overall_insights.md`

- You organize material into **sections and subsections** (e.g. VLAs → system architecture).
- Each section has **numbered insight bullets** that synthesize ideas and **cite papers by name** in parentheses—`(ERA)`, `(DualVLA)`, not sub-bullets from `select_papers`.
- When a section grows too large, you **subgroup** and reshuffle—again by hand.

### 2.4 What makes this costly

- **Linear files** do not scale: scrolling, search, and mentally holding cross-links.
- **Reorganization** (splits, regrouping) is repetitive editing, not a stable structure.
- **Depth is uneven** by design: all sources are gist + insights-visible; only a **subset** gets `select_papers`-level depth—but the **medium is the same** for everything, which blurs tiers in practice.

### 2.5 Reference artifacts (robotics exemplar)

These files document **one real project** (robotics / embodied AI), not the only domain Me-Mex supports. They serve as **acceptance fixtures** for shape and import:

| File | Role |
|------|------|
| [`docs/deeper_read_notes.md`](../../docs/deeper_read_notes.md) | Catalog tier |
| [`docs/select_papers.md`](../../docs/select_papers.md) | Deep-read tier |
| [`docs/overall_insights.md`](../../docs/overall_insights.md) | Cross-paper tier |

Other workstreams use the **same three-tier pattern** in separate project workspaces (see [§5.2](#52-multiple-projects)).

---

## 3. What motivates v2

**Me-Mex v1** (tag `v1`) proved ingestion, mutability, and graph visualization, but for daily research it felt **too autonomous** (long LLM chains for traversal, linking, and reorg) and **too slow**, with **limited direct control** over where knowledge lives. The primary interface was a **scrollable text chat**, not a research workflow shaped like your notes.

v2 keeps a **graph and agents**, but optimizes for:

1. **The same three tiers** as your markdown, not a single “ingest everything” pipeline—**separate tools** for gist, intra-document graph, linking, and reorg, each invoked only when you ask.
2. **Talk first, persist on command**—summaries and Q&A without automatic graph mutation.
3. **Voice-first interaction** (LiveKit) with **voice rail + default recommendations dock** (latest reply + nudges + **every pending approval**), not a full chat history wall.
4. **Explicit graph edits** (nodes, edges, placement, todos) with approval on risky changes.
5. **Faster retrieval** via a **LoRA decision adapter** that scores **relevance of every BFS frontier node** w.r.t. the current **query concept**—replacing v1 **per-hop generative `subgraph_expansion`**. Trained from **legacy notes** + traces first, then live expands. [05-models-and-runtime.md](./05-models-and-runtime.md).

---

## 4. North star

**You are the editor-in-chief.** The agent is a fast, interruptible coworker for **ordinary Q&A** as well as graph work. **Nothing is persisted to the graph until you explicitly ask for it** (or approve a proposed diff).

---

## 5. The target system

### 5.1 Three tiers in the graph

| Tier | Today (markdown) | Me-Mex |
|------|------------------|--------|
| **Catalog** | `deeper_read_notes.md` — short gist per source | Document **`ROOT`** with gist; no intra-doc graph by default |
| **Deep read** | `select_papers.md` — detailed bullets per important source | **Intra-document subgraph** under that ROOT (immutable concepts + passages); you review before commit |
| **Cross-paper insights** (habit) | `overall_insights.md` — sections, numbered bullets, paper cites | **`CONCEPT_M`** hubs + **`INSIGHT`** nodes you save; links to **`ROOT`**; same mutable machinery as notes |

**Catalog vs deep read:** in your workflow, **gist-only `ROOT`s are the norm** for volume, but **each one is still meant to participate in insights** (via **`ROOT` → section/insight** when you connect—no notion of “catalog-only, never in insights”). The **selective** step is **deep read**, not admission into the insights tree. Nothing auto-wires; you still choose when each **`ROOT`** links.

**Reading depth is opt-in:** nothing runs as a fixed bundle. Linking, reorg, and intra-document extraction are **never** implied by each other or by a casual question.

**Sources** are any **text-based documents** you can fetch and normalize—arXiv PDFs, blogs, substacks, HTML articles (v1-style extractors such as **trafilatura**), local files, and similar—not “papers only.” Robotics markdown is paper-heavy; other projects may be blog- or note-heavy. Each ingested source still gets one **`ROOT`** (paper, post, transcript, etc.).

**Gist** is the catalog tier on that ROOT. Two valid paths:

- **You provide the gist** — speak or type it; agent creates or updates the ROOT with your text (minimal or no LangChain).
- **Agent-assisted gist** — you pass a URL (or ask after inquiry); agent may **fetch + summarize** via LangChain/LLM to produce candidate gist text—in the **dock** first, then on **`ROOT`** only if you commit.

**Composable operations (implementation intent):** **worker agents** (LLM / decision model) plus **deterministic tools** for each operation—no v1-style monolithic ingest path ([04-agent-orchestration.md](./04-agent-orchestration.md) §5–6):

| Operation | What it does | When it runs |
|-----------|----------------|----------------|
| **Set / update gist** | Create or edit **`ROOT`** summary text | You commit, with or without prior LLM assist |
| **Build intra-document graph** | Fetch, chunk, extract concepts; stage → commit under ROOT | You ask for deep read only |
| **Link / place** | Suggest or add edges (e.g. ROOT → insights section) | You ask for placement or linking only |
| **Reorganize** | **Decision-model recommendations** (splits, relocations, orphans)—not v1 generative reorg | You ask for reorg; review suggestions; **apply** only after approval |

LangChain / Ministral work runs in **agents** (inquiry, gist assist, intra-doc extract, placement scoring)—but each **graph effect** is tied to an **approved deterministic tool** (or your explicit command), not to “open a URL.”

### 5.2 Multiple projects

Me-Mex is **multi-project** (as v1 had project switchers). Each workspace is an island:

- Own **Genesis** / **project introduction** (scope text), graph, catalog, deep-read subgraphs, and insights tree.
- Shared agent stack and tools; **no** cross-linking or merging across projects unless you explicitly import or copy.

### 5.2.1 Project scope (onboarding—not `domain_mode`)

There is **no** `domain_mode` or Research / AI Safety / Math switch. **Broad context** for the whole agentic workflow comes from **project fields**—primarily a short **introduction** filled **in conversation** before you ingest anything:

- When you **create or open** a project, the agent run loads project fields. If **introduction / project details** are empty, routing stays **conversation-only** until scope is saved (or you explicitly override).
- The voice agent’s **first job** is to ask: *“What is this project about?”*
- You describe goals, topic, and framing in **voice** (dock shows the exchange); the agent may ask one or two clarifying follow-ups.
- That thread sets how **inquiry summaries** and recommendations are framed until you change scope—it is **not** graph ingest.
- When you approve, the text is **persisted** (project record + Genesis scope description) and injected into **every** downstream LLM call—gist assistance, placement, reorg suggest—**before** you add sources.
- You can **revise scope** later by voice (“update project intro to …”); same fields, explicit commit.

Robotics, math, or safety work are just **different project intros**—same graph kinds and tools.

### 5.3 What lives where

| Kind of content | Where it lives |
|-----------------|----------------|
| Durable knowledge (canvas) | **Only** the node kinds in [03 §5](./03-graph-and-memory.md#5-canvas-node-kinds)—**`ROOT`**, **`CONCEPT_I`**, **`CONCEPT_M`**, **`INSIGHT`**, **`NOTE`**, **`TODO`**—plus **uniform links** ([§4](./03-graph-and-memory.md#4-canvas-vs-database) for off-canvas stores) |
| Document gist | On the source **`ROOT`** |
| Highlights you cherry-pick from a reply | **`NOTE`** or **`INSIGHT`** when you ask to save—they are the same class of mutable node |
| Extracted claims from a deep read | Immutable **`CONCEPT_I`** under **`ROOT`**; **`passages`** in Mongo for the agent, **not** on the canvas |
| Takeaways you name as “insights” | **`INSIGHT`** nodes you commit explicitly—**not** a separate document tier |

The **recommendations dock** (latest turn + **all nudges and approvals**) is where you read, approve, or dismiss every proposed change; the **graph** is for keeping. UX: [02-user-experience.md](./02-user-experience.md).

### 5.4 Linking rule: paper cites → document ROOT only

When an **`INSIGHT`** (or hub) should cite a **source**, links attach to the source **`ROOT`**—not through intra-document concept leaves. Every source is one **`ROOT`**, whether gist-only or deep-read.

| ROOT state | Under the ROOT | How insights connect |
|------------|----------------|----------------------|
| **Gist only** | Title + gist | **You** create **`ROOT` ↔ section/insight** edges when you choose |
| **Deep read** | Local subgraph of immutable concepts (optional) | **Same rule:** insights cite **`ROOT` only**, not individual intra-document concepts—unless you later ask for a different edge |

**Deep read ≠ auto-wiring your mutable graph.** “Create the intra-doc graph” is local to that **`ROOT`**. It does **not** auto-link hubs, auto-parent under Genesis, or attach **`INSIGHT`** nodes to extracted concepts. The agent may **suggest** placement; **you** approve links like any other edge.

This mirrors `overall_insights.md`: citations are **papers** `(ERA)`, not internal `select_papers` subsections.

---

## 6. Working with the agent

The agent is **not** graph-only. Use it for summaries, follow-ups, and comparisons with **no obligation to store anything**.

### 6.1 Conversation vs persistence

| Intent | Example | Effect on graph |
|--------|---------|-----------------|
| **Inquiry / gist talk** | arXiv in fields → “what’s the gist?” | **None**; gist lives in **conversation** until **recommendation** or explicit create ROOT |
| **Light commit** | “Create ROOT; gist is …” / “add ToDo Y” | GistWorker / scratch tools—may skip recommendation when you supply full text |
| **Rich commit** | After a thread: “Create ROOT and three concepts; wire them.” | ROOT + concepts + edges you name; approval on non-trivial diffs |
| **Deep read** | “Build the intra-doc graph for this URL/ROOT.” | **IntraDocWorker** (LLM) → staging → commit tool under ROOT (no auto link/reorg) |
| **Placement** | “Where should this **source** fit?” | **LinkPlaceWorker** (DecisionScorer) → dock → link tool on approve |
| **Reorg** | “Split this section …” | **ReorgRecommendWorker** → diff in dock → apply tools on approve |

**Topic threads:** several turns on one paper can live in **session/topic memory** for follow-ups. That is not a permanent project chat log and not a substitute for the graph.

### 6.2 Typical sessions

See **[06-workflows.md](./06-workflows.md)** for the full journey. In order:

0. **Create project** (UI/API) → **unmute** → **P1** scope conversation (what / where / why / source paradigm) → scope saved → free to ask anything.  
1. **Gist talk** — arXiv in fields → gist in dock (**no ROOT** yet); discuss; **recommendation** or command to create ROOT.  
2. **Deep read** — recommended after long thread, from existing ROOT, or direct URL command; review concepts → approve commit.  
3. **Link / reorg** — recommendations after new nodes or crowded hubs—or manual “connect A to B”; options then approve.  
4. **Retrieval** — you ask; optional ToDo-related recommendation only.

Plain-language **persist** commands map to tools; non-trivial changes show a **diff** when appropriate.

### 6.3 Modes at a glance

| Mode | Typical trigger | Graph effect |
|------|-------------------|--------------|
| Inquiry | “What does this link/paper do?” | UI only (LLM/fetch ok) |
| Gist commit | Your text **or** saved summary → ROOT | **Gist tool** → create/update **ROOT** |
| Deep read | “Create the intra-doc graph.” | **IntraDocWorker** → commit tools → subgraph under ROOT |
| Placement | “Where does this source fit?” | **LinkPlaceWorker** → **ROOT** links after you confirm |
| Reorg | “Split / merge / relocate …” | **ReorgRecommend** / **ReorgApply** agents + tools |

---

## 7. Design principles

1. **Human-in-the-loop by default** — No silent auto-reorg, auto-merge, or auto-link at scale. Suggestions come as diffs; you approve, edit, or discard. v1-style autonomous ingest becomes **staged proposals** and **opt-in depth**.

2. **Three-tier ladder, not one pipeline** — Catalog many papers; deep-read few; weave into the insights tree on your schedule.

3. **Voice rail + default dock** — LiveKit mute/unmute; **custom fields** on the rail; **right dock always on** with **latest exchange** + **recommendations** (nudges and **HITL approvals** in one list—not v1 scrollback, not orphan modals). Optional short **topic thread** in session. Typed values in JSON so STT does not corrupt tools.

4. **Conversation and graph are separate** — Exploration is first-class; **graph writes are explicit**, never implied by a summary request.

5. **Full graph controllability** — CRUD on mutable nodes, edges, placement, status (e.g. ToDo), manual connections. **One link kind**, equal weight everywhere. **`INSIGHT`** is just another mutable kind (like **`NOTE`**), not a document tier. **Gist, intra-doc, link, and reorg are separate agent paths** with **deterministic** persist tools. When citing sources, link **`ROOT`** on your schedule. Placement is **advisory**.

6. **Immutable evidence stays sacred** — Intra-document concepts and source roots are write-once; synthesis lives in mutable structure.

7. **Insights maintenance is assisted, not automatic** — Crowded sections: **decision model** scores relevance of frontier targets w.r.t. query nodes; agent shows **recommendations** and a diff—you approve before any apply. **No** v1 `SPLIT_CONCEPT` / `reorganize_overclustered_nodes` token cascade.

8. **Speed where it matters** — **One relevance vector per hop** over the full frontier (then agent top‑k expand); heavy LLM only for deep extract and synthesis you request—not v1-style generative BFS text per hop.

9. **Observable agent runs** — LangGraph **checkpoints**, **`jobs` ledger**, `tasks`/custom streams, and tool logs so you always know what each ask is doing and what awaits approval.

10. **Decision model is in scope for v2** — Placement and traversal use a **LoRA adapter** on Ministral 3 8B from **day one**: bootstrap labels from curated markdown, **train/eval before** interactive placement ships, deploy on Colab vLLM alongside chat—same commitment level as Whisper-tiny and Kokoro. Live traces refine the adapter over time. See [05-models-and-runtime.md](./05-models-and-runtime.md).

11. **Evolve v1 backend when useful** — **MongoDB** for graph storage; **optional** reuse of v1 parsers, passages, and consolidation **only where** they fit composable tools and **deep-read mode**—never port v1 behavior that contradicts this spec. See [08-migration-and-reuse.md](./08-migration-and-reuse.md).

---

## 8. v2 platform plan (committed)

| Layer | Choice |
|-------|--------|
| **Graph DB** | **MongoDB** (evolve v1 collections; no SQLite clean-slate) |
| **Chat / tools LLM** | **Ministral 3 8B** on Colab **vLLM** |
| **Decision model** | **LoRA adapter** (Ministral 3 8B) from **notes bootstrap** + live traces — **no logprob MVP** |
| **Voice STT** | **Whisper-tiny** |
| **Voice TTS** | **Kokoro** |
| **Real-time voice** | **LiveKit** agent + LangGraph |
| **Orchestration** | **LangGraph** / LangChain agents, **explicit tools** only |

**Product invariants (not negotiable for v2):** no **implicit graph ingest** from chat; no **overnight autonomous co-scientist** that mutates the graph without you. Graph changes require **explicit commands** or **approved** diffs.

**Phasing (same release family):** **notes → JSONL → LoRA train/eval → deploy** before voice placement/highlight rely on DecisionScorer; then interactive graph + voice on the full stack. **Every spec topic** maps to a phase in [09-phasing.md](./09-phasing.md) (coverage matrices + workflow/tool checklists).

---

## 9. Success criteria (personal research)

- **Summary without mutation** — optional one-sentence promote to ROOT, note, or **ToDo**; **ToDo → `CONCEPT_M`** when you return to the work.
- **Short thread → commit** — paper + N concepts + edges when you instruct, with approval when needed.
- **Catalog at scale** — many gist commits without full extract or reorg.
- **Deep read** — one paper through staging without maintaining `select_papers.md` by hand.
- **Placement** — “where does this fit?” with top candidates; **you** wire **ROOT** to insights.
- **Insights tree** — sections, numbered synthesis, **subgroup** via approved diff.
- **Retrieval** — highlighted subgraph quickly, not opaque long agent chains.
- **Voice + canvas** — single color-coded graph; **recommendations dock** for latest reply + nudges (not scrollback chat).
- **Multi-project** — e.g. robotics vs another PI, isolated graphs, clean switching.
- **Decision quality** — **LoRA** meets held-out **relevance-ranking** eval (`query_node` + full `frontier` → labeled relevant ids) from notes / v1 traces before retrieval and suggest paths ship.

---

## 10. Related specification

| Document | Topic |
|----------|--------|
| [02-user-experience.md](./02-user-experience.md) | Voice rail, recommendations dock, unified color-coded canvas |
| [05-models-and-runtime.md](./05-models-and-runtime.md) | Ministral, decision bootstrap from notes, speech stack |
| [08-migration-and-reuse.md](./08-migration-and-reuse.md) | What to port from tag `v1` |
| [10-open-questions.md](./10-open-questions.md) | Open product and architecture decisions |
| [11-testing.md](./11-testing.md) | Unit, integration, e2e, CI gates |
| [README.md](./README.md) | Full spec index |
# Graph-Memex (`me-mex`) Complete UI/UX & System Architecture Specification

**Date:** 2026-09-21  
**Status:** Comprehensive Architecture & UI/UX Spec  
**Target File:** [`me-mex/ui_spec.md`](file:///Users/vedpatwardhan/Desktop/cortex-os/me-mex/ui_spec.md)  

---

## 1. High-Level Vision & Core Paradigm

**Graph-Memex (`me-mex`)** is an expansive, voice-first, interactive research workspace designed for cross-domain literature ingestion, associative concept discovery, voice-driven hypothesis synthesis, and node-grounded report generation.

### Key Architectural Concepts

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 THE MEMEX ECOSYSTEM                                    │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│   RAW STREAMING INTAKE              GLOBAL KNOWLEDGE GRAPH         LOCAL PROJECT WORKSPACE │
│  ┌──────────────────────┐          ┌─────────────────────────┐    ┌──────────────────┐ │
│  │ • PDFs / Papers      │ ───────> │  The Master Superset    │ ─> │ Focused Project  │ │
│  │ • Web Links / Tweets │ Ingest & │  (Multiple Paradigms,   │    │ Subgraph /       │ │
│  │ • Video Transcripts  │ Merge    │   Human Insights,       │    │ Task Notepad     │ │
│  │ • Voice Epiphanies   │          │   Agent Hypotheses)     │    └──────────────────┘ │
│  └──────────────────────┘          └─────────────────────────┘                         │
│                                                 │                                      │
│                                                 ▼                                      │
│                                    NODE-GROUNDED REPORT STUDIO                         │
│                                    ┌─────────────────────────┐                         │
│                                    │ Color-Coded Markdown    │                         │
│                                    │ Interactive Provenance  │                         │
│                                    └─────────────────────────┘                         │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

1. **Global Graph (The Master Superset):** A single, unified database holding all ingested documents, human voice insights, agent-generated hypotheses, and cross-paradigm connections. It contains no rigid single root node; instead, distinct paradigms form natural clusters in semantic space.
2. **Local Project Workspaces (Focused Subgraphs):** Task-specific working spaces (e.g., *"VLA Policy Benchmarking"* or *"Skeletal Prior Integration"*). **Superset Rule:** The Global Graph is ALWAYS the master. Adding or editing any node/edge in a Local Project Workspace updates the Global Graph first, which then projects back into the Local Workspace.
3. **Voice-First Grounded Interface:** Minimal text boxes (restricted to URL entry). Interactions happen primarily via voice streams (Web Audio API / Whisper), where the agent visually highlights traversal paths and target subgraphs in real time while conversing.
4. **Bi-Directional Seeded Ingestion:** Uploading a PDF, tweet, or voice note creates an initial *local document subgraph*. These nodes act as seeds to query the Global Graph, performing bi-directional discovery: existing graph nodes guide deep re-parsing of the document, and multi-agent debates resolve node merges and ambiguities.
5. **Interactive Node-Grounded Reports:** Markdown reports generated for any topic or subgraph feature color-coded phrase highlights linked directly to source graph nodes. Hovering or clicking a phrase highlights the exact provenance node on the canvas.

---

## 2. Tech Stack & Architectural Decisions

### 2.1 Single-Page Application (SPA) Architecture
**Decision:** **Single-Page Application (SPA)** with a persistent canvas workspace and fluid view-switching drawers. 
* **Why SPA?** Keeping the 3D/2D WebGL canvas (`react-force-graph`) mounted across view transitions prevents expensive WebGL re-initialization and graph re-renders. View shifts (Global Graph $\leftrightarrow$ Local Project Workspace $\leftrightarrow$ Report Studio) update filters and camera constraints smoothly without page reloads.

### 2.2 Complete Tech Stack Blueprint

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                   TECH STACK BLUEPRINT                                 │
├──────────────────────────┬─────────────────────────────────────────────────────────────┤
│ Frontend Framework       │ Next.js 15 (SPA Client Mode) + React 19 + TypeScript        │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ UI & Styling             │ Tailwind CSS v4 + Shadcn UI + Radix Primitives + Lucide     │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ Graph Visualization      │ react-force-graph-2d / react-force-graph-3d (Three.js WebGL)│
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ Voice & Audio Engine     │ Web Audio API (MediaRecorder) + Whisper API / fast-Whisper  │
│                          │ Web Speech API / ElevenLabs TTS for agent voice responses   │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ State & Realtime Sync    │ Zustand (Canvas/UI state) + SSE (Server-Sent Events)        │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ Backend API              │ Python FastAPI (FastMCP compatible)                         │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ Primary Database         │ MongoDB (Local-first: `nodes`, `edges`, `raw_docs`, `projects`)│
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ Web Snapshot & Printer   │ Playwright / Puppeteer headless browser service             │
├──────────────────────────┼─────────────────────────────────────────────────────────────┤
│ LLM Engine               │ Ministral 3 8B (running via Colab / Local vLLM endpoint)    │
└──────────────────────────┴─────────────────────────────────────────────────────────────┘
```

---

## 3. Detailed UI Layout & View Modes

The SPA features four synchronized view modes accessible via a floating top mode-switcher:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  [🌐 Global Graph]   [📁 Project Workspace]   [📄 Report Studio]   [📥 Intake Stream]   │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  PANE 1: VOICE & INGESTION    PANE 2: LIVE CANVAS & TRAVERSAL   PANE 3: READER & PROVENANCE│
│  (Left Rail - 20%)            (Center Canvas - 55%)             (Right Drawer - 25%)    │
│                                                                                        │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### 3.1 Pane 1: Left Rail (Voice Control & Ingestion Panel)

* **Upload & Intake Dropzone:**
  - File Drop Area (PDFs, Markdown notes, video transcript JSONs, image snapshots).
  - Web Link Box: Enter URL $\rightarrow$ triggers headless Playwright service to snapshot HTML/tweet, convert to clean Markdown, and archive raw file.
  - Quick Voice Epiphany Button (`🎙️ Hold / Click to Speak`): Stream spoken thoughts directly. Fast-Whisper transcribes audio, and a mini-ingestion pipeline extracts atomic nodes and links them to the graph.
* **Temporal / Chronological Tracker:**
  - Chronological timeline filter (e.g., `2024 Demos` vs `2026 Breakthroughs`).
  - Allows tracing how concepts evolved over time across papers and video transcripts.
* **Local Project Workspace Selector:**
  - Switch between active project scopes (e.g., *Global Graph*, *Project: VLA Control*, *Project: Skeletal Priors*).
  - Shows active project node count and superset sync status.

---

### 3.2 Pane 2: Center View (Live Graph Canvas & Traversal Visualizer)

* **WebGL Force Graph (`react-force-graph`):**
  - Continuous 2D/3D rendering of the knowledge graph.
  - **Node Color Taxonomy:**
    - 🔵 **Primary External Sources** (PDFs, papers, web articles, tweets, video transcripts).
    - 🟨 **Human Personal Insights** (Voice epiphanies, manual notes, user thoughts).
    - 🟣 **Agent-Synthesized Hypotheses** (Co-Scientist generated bridge nodes).
    - 🟩 **Atomic Concept / Phrase Nodes** (HippoRAG 2 phrase layer).
    - 🔴 **Falsified / Dead-End Nodes** (Archived failed paths with strikethrough visual styles).
  - **Edge Style Encoding:**
    - **Solid Lines (High Stiffness):** Direct structural dependencies (`BUILDS_UPON`, `DERIVES_FROM`).
    - **Dashed Splines (Low Stiffness):** Soft thematic membership or co-citation.
    - **Red Directional Arrows:** Contradictions or falsification (`REFUTES`, `CONTRASTS_WITH`).
* **Live Ingestion & Traversal Overlay:**
  - As a new document or voice note is ingested, the canvas displays **real-time visual traversal lines**:
    - Highlights the local document seed nodes in glowing gold.
    - Animates pulse waves along graph edges showing where the agent is traversing, searching, and evaluating potential merges.
    - Renders an **Agent Conflict Badge** when agents debate a merge, allowing 1-click human resolution if requested.

---

### 3.3 Pane 3: Right Drawer (Markdown Reader, Editor & Provenance Inspector)

* **Contextual Reader:**
  - Renders raw source document text, converted web snapshot Markdown, or transcribed voice note.
  - Highlighted 2-line executive takeaway box.
  - Visual metadata: Publication date, temporal sequence, original URL/DOI link.
* **Interactive Connections Panel:**
  - Incoming ($\leftarrow$) and Outgoing ($\rightarrow$) edge list.
  - Manual connection drawer to draw new links verbally or via autocomplete.

---

## 4. Specific Workflows & Feature Specifications

### 4.1 Bi-Directional Ingestion & Multi-Agent Debate Engine

```
[ User Input (PDF / URL / Voice Note) ]
                 │
                 ▼
[ Local Document Subgraph Extraction ] (Extract local concepts, claims, assumptions)
                 │
                 ▼
[ Seed-Guided Global Graph Traversal ] (Query Global MongoDB via HippoRAG 2 PPR)
                 │
       ┌─────────┴─────────┐
       ▼                   ▼
[ Global Node Merges ]  [ Re-parse Document ] (Existing graph context guides re-extraction)
       │                   │
       └─────────┬─────────┘
                 ▼
[ Multi-Agent Debate Verification ] (Agents challenge correlation / resolve ambiguities)
                 │
       (Uncertainty Flagged?)
       ├── YES ──> [ Voice Prompt User: "How is X different from Y?" ]
       └── NO  ──> [ Commit to Global Graph & Project Workspace ]
```

1. **Local Subgraph Extraction:** Parsing an uploaded PDF, web print, or voice note extracts key claims and sub-assumptions.
2. **Seed-Guided Search:** Local nodes act as seeds to search the Global Graph using vector similarity and Personalized PageRank (PPR).
3. **Bi-Directional Feedback:** Existing graph nodes guide the agent back into the ingested document to extract nuances missed during the first pass.
4. **Agent Debate Verification:** A comparative multi-agent debate architecture evaluates node merges and relationship accuracy. If agents remain uncertain, the system prompts the user verbally: *"I found high similarity between X and Y. Should I merge them or create a CONTRASTS_WITH connection?"*

---

### 4.2 Voice-First Conversational Agent

* **Zero Large Text Boxes:** Conversation occurs via continuous voice streaming or push-to-talk.
* **Grounded Canvas Navigation:** When speaking to the agent:
  - User: *"What do we have on skeletal priors for bipedal control?"*
  - Agent: *Submits query, camera smoothly pans/zooms to the relevant subgraph cluster, dims unrelated nodes, and highlights target nodes in pulsing blue.*
  - Agent Spoken Response: *"We have 3 papers and 1 voice insight from last week. Paper A proposes IK constraints, while your voice note suggested physics-based loss terms. Would you like me to check for contradictions between them?"*
  - User: *"Yes, search for contradictions."*

---

### 4.3 Global Graph vs. Local Project Workspaces

* **Superset Guarantee:** The Global Graph is the master repository.
* **Local Project Workspace Scope:**
  - Creating a Project Workspace (e.g., *"Project: Skeletal MPC"*) creates a constrained visual slice of the Global Graph.
  - When the user adds a new paper or voice note while inside a Local Workspace, the system:
    1. Ingests and merges data into the **Global Graph** first.
    2. Projects the relevant nodes/edges into the active **Local Project Workspace**.
  - Local nodes display a badge indicating their global parent context.

---

### 4.4 Interactive Node-Grounded Report Studio

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ REPORT STUDIO: "Skeletal Priors in Humanoid Control"                                    │
├──────────────────────────────────────────┬─────────────────────────────────────────────┤
│ MONACO / MARKDOWN EDITOR                 │ LIVE NODE PROVENANCE MAP                    │
│                                          │                                             │
│ # Executive Summary                      │  [Paper: PhysCtrl 2026] (Blue Node)          │
│                                          │         │                                   │
│ <span class="bg-blue-100">               │         ▼                                   │
│ Physics-based skeletal priors reduce     │  [Voice Note: May 12] (Yellow Node)         │
│ search space by 40% in humanoid MPC.     │         │                                   │
│ </span>                                  │         ▼                                   │
│                                          │  [Hypothesis #4] (Purple Node)              │
│ <span class="bg-yellow-100">             │                                             │
│ However, joint limits must be calibrated │ Clicking any highlighted text pans canvas   │
│ dynamically during contact transitions.  │ directly to its source node!                │
│ </span>                                  │                                             │
└──────────────────────────────────────────┴─────────────────────────────────────────────┘
```

1. **Report Generation:** User asks: *"Generate a report on Skeletal Priors in Humanoid Control."*
2. **Markdown Synthesis:** The agent compiles a Markdown report saved to storage.
3. **Interactive Provenance Visualizer:**
   - Report text features **color-coded inline highlights** corresponding to source nodes:
     - 🟦 Blue highlights = Data sourced from external papers/PDFs.
     - 🟨 Yellow highlights = Data sourced from human voice insights.
     - 🟪 Purple highlights = Data sourced from agent-synthesized hypotheses.
   - Hovering/clicking any highlighted phrase smoothly pans the graph canvas to the exact source node and opens its provenance snippet.
   - User can refine the report via voice: *"Update section 2 using our recent voice insight on torque limits."*

---

## 5. MongoDB Data Schemas & Pseudo-Contracts

```typescript
// 1. Raw Document / Web Intake Record
interface RawDocument {
  _id: string;
  source_type: 'pdf' | 'web_snapshot' | 'tweet' | 'video_transcript' | 'voice_epiphany';
  title: string;
  raw_content: string; // Cleaned Markdown text
  original_url?: string;
  file_path?: string;
  created_at: Date;
  temporal_timestamp: Date; // Real-world event/publication date
}

// 2. Global Graph Node Schema
interface GraphNode {
  _id: string; // Unique node ID
  node_type: 'external_source' | 'human_insight' | 'agent_hypothesis' | 'concept_phrase' | 'falsified_path';
  title: string;
  takeaway_2line: string;
  raw_doc_id?: string; // Link to RawDocument
  project_ids: string[]; // List of Local Project Workspaces this node belongs to
  metadata: {
    authors?: string[];
    url?: string;
    elo_score?: number; // For hypothesis nodes
    fsrs_due_date?: Date; // For spaced repetition queue
  };
  embedding_vector?: number[]; // 1536-dim vector for semantic search
  created_at: Date;
  updated_at: Date;
}

// 3. Global Graph Edge Schema
interface GraphEdge {
  _id: string;
  source_node_id: string;
  target_node_id: string;
  edge_type: 'BUILDS_UPON' | 'CONTRASTS_WITH' | 'REFUTES' | 'DERIVES_FROM' | 'CATEGORY_MEMBER';
  weight: number;
  provenance_quote?: string;
  project_ids: string[];
  created_at: Date;
}

// 4. Local Project Workspace Schema
interface ProjectWorkspace {
  _id: string;
  name: string;
  description: string;
  node_ids: string[]; // Subgraph node IDs (subset of Global Graph)
  edge_ids: string[]; // Subgraph edge IDs
  created_at: Date;
}
```

---

## 6. Implementation Roadmap & Milestones

1. **Milestone 1: SPA Canvas & Layout Prototype (Frontend Mock)**
   - Build Next.js 15 SPA shell with 3-pane layout and top view switcher (Global Graph, Project Workspace, Report Studio).
   - Integrate `react-force-graph-2d/3d` with mock JSON dataset color-coded by node taxonomy.
   - Implement slide-out Markdown reader drawer and top search toolbar.
2. **Milestone 2: Voice Engine & Web Ingestion Service**
   - Integrate Web Audio API streaming with Fast-Whisper for voice insight intake.
   - Build Python Playwright web printer service to snapshot URLs/tweets into clean Markdown files.
   - Set up local-first MongoDB schema (`raw_docs`, `nodes`, `edges`, `projects`).
3. **Milestone 3: Bi-Directional Ingestion & Traversal Engine**
   - Implement local document subgraph extraction and seed-guided HippoRAG 2 PPR traversal.
   - Add live animated canvas traversal lines showing real-time agent graph traversal.
   - Build multi-agent debate verification layer for node merges and conflict resolution.
4. **Milestone 4: Project Workspaces & Interactive Report Studio**
   - Implement Global Graph $\leftrightarrow$ Local Project Workspace superset sync logic.
   - Build Node-Grounded Report Studio with color-coded phrase highlights linked to canvas nodes.
   - Integrate Ministral 3 8B (Colab/vLLM) for background extraction, synthesis, and voice conversation.

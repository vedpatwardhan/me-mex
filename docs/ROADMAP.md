# Me-Mex Master Execution Roadmap

> **Document Purpose**: This document outlines the strategic execution roadmap for **Me-Mex**, detailing the 5-phase engineering progression from backend implementation to specialized model fine-tuning for Cortex-OS.

---

## 1. Executive Summary & Strategic Vision

**Me-Mex** is an agentic external memory system designed as an external extension of your brain for organizing, synthesizing, and retrieving textual knowledge (academic papers, technical blogs, YouTube transcripts, reports, X posts).

The roadmap bridges core engine implementation with real-time UI interactivity, end-to-end empirical verification, and eventual custom model fine-tuning to transition from a memory subsystem into a broader agentic operating system (**Cortex-OS**).

---

## 2. The 5-Phase Strategic Execution Roadmap

```
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │                         THE 5-PHASE EXECUTION ROADMAP                                  │
 └────────────────────────────────────────────────────────────────────────────────────────┘

  [ Goal 1: Core Engine & Substrate Implementation ] — COMPLETED
   ├── Ingestion Pipeline: Out-of-graph text chunk storage in `passages` collection
   ├── Clean 3-Element Topology: Root Nodes, Intra-Doc Concepts, Persona Domain Hubs, & Typed Edges
   ├── Node Mutability Enforcement: Root & Intra-Doc nodes (Immutable), Domain Hubs (Mutable)
   ├── Mutually Exclusive Hub Partitioning: rustworkx unweighted eigenvector hub detection
   ├── Single-Source Genesis Hub: Primordial 'Everything' hub anchor across workspaces
   ├── Phase 3.5 Dynamic Target Generalization: Post-linking LLM pass widening mutable target scope
   └── Scenario-Aware Reorganization ($n // 2$): Degree halving compression with compulsory hub updates

  [ Goal 2: Comprehensive Backend Testing & Telemetry ] — COMPLETED
   ├── Unit Test Suite: 50+ passing tests with 2-worker isolation (`pytest -n 2`)
   ├── Project Isolation Tests: Scoped graph querying (`project_id`) & workspace chat history
   ├── Persona Exploration & Reorganization Tests: Voronoi partitioning, outward leaf movement & degree caps
   ├── Target Generalization Tests: Validated title/description synthesis & Genesis title preservation
   ├── Fail-Fast Ingestion Coordination: Zero orphan document records on fetch failures
   └── Full Local LLM Telemetry Tracing: Structured logging of prompts, completions, latencies, and caller IDs to `backend/logs/llm_traces/`

  [ Goal 3: Frontend Implementation & Visualizer Integration ] — COMPLETED
   ├── WebGL Force Graph Canvas: 2D force graph (`react-force-graph-2d`) with dynamic physics
   ├── Dynamic Palette Telemetry: Live visual node glowing mapped to active persona departments over SSE
   ├── Streamlined Node Description Drawer: Simplified Description panel with fallback to content
   ├── Header & Action Controls: Clean single-badge headers and node deletion confirmation modal
   ├── Canvas Search: Unified indexing over node title, ID, and description text
   └── Speech-to-Text Dictation: In-browser Whisper-base.en transcription via WebAssembly/WebGPU

  [ Goal 4: End-to-End System Testing & Graph Interactivity Enhancements ] — ACTIVE
   ├── Continuous Ingestion Validation: Automated multi-document intake, search retrieval, & chat stream checks
   ├── Taxonomic Depth Ceilings: Monitoring cascade depth ($D_{\max}$) and transition to lateral clustering
   ├── Interactivity Enhancements: Drag-and-drop intake staging sandbox, dynamic re-clustering
   └── Report Studio Integration: Graph-grounded markdown synthesis and manuscript draft generation

  [ Goal 5: Model Fine-Tuning & Cortex-OS Foundation ] — LONG-TERM
   ├── Synthetic Dataset Curation: Ingestion transcripts, sub-graph traversals, & reorganization actions
   ├── Ministral Model Fine-Tuning: Fine-tuning local Ministral 3-8B / Colab vLLM server
   └── System Integration: Expanding Me-Mex memory into a broader agentic operating system (Cortex-OS)
```

---

## 3. Detailed Phase Specifications

### Goal 1: Core Engine & Substrate Implementation
- Build out `app/db.py`, `app/models.py`, `app/services/graph_analytics.py`, and `app/services/llm_gateway.py`.
- Implement clean 3-element topology (Root Nodes, Intra-Doc Concepts, Persona Domain Hubs, and Relation Edges).
- Enforce strict **Node Mutability Hierarchy**: Root Nodes and Intra-Doc concepts are `immutable: True`; Persona Domain Hubs and Intermediate nodes are `immutable: False`.
- Implement 3 execution paths (`CONVERSATION`, `RETRIEVAL`, `INGESTION`) where Retrieval and Ingestion run sub-graph traversal and relevance evaluation before triggering the final conversation response.
- Partition graph into mutually exclusive sub-graph regions across `rustworkx` unweighted eigenvector hubs.

### Goal 2: Comprehensive Backend Testing Pipeline
- Construct complete unit test suite in `tests/` covering database models, project workspace isolation, and FastMCP search tools.
- Verify path routing for `CONVERSATION`, `RETRIEVAL`, and `INGESTION`.
- Test independent persona sub-graph traversal, relevance evaluation, and passage-grounded concept splitting (`SPLIT_CONCEPT`).
- Validate SSE telemetry streaming (`GET /api/sse/chat`) ensuring real-time `node_touched` and traversal events emit cleanly.

### Goal 3: Frontend Implementation & Visualizer Integration
- Implement Vite React client featuring `react-force-graph-2d` for interactive visual node visualization.
- Connect frontend SSE client to render real-time glowing node IDs during persona traversal and concept reorganization.
- Implement streamlined slide-out **Description** panel replacing legacy Zettelkasten cards with clean topic descriptions.
- Standardize header presentation with single node-type badges and node deletion confirmation modal.
- Connect canvas search over node descriptions, titles, and IDs.
- Integrate in-browser speech-to-text dictation using Whisper-base.en via WebAssembly/WebGPU.

### Goal 4: End-to-End System Testing & Graph Interactivity Enhancements
- Conduct end-to-end empirical testing across multi-document PDF/web ingestion, associative recall, and report generation.
- Enhance graph canvas interactivity with node dragging, manual edge creation, node merging, and intake staging sandbox approval toggles.
- Build Report Studio enabling node-grounded markdown report drafting and export.

### Goal 5: Model Fine-Tuning & Cortex-OS Foundation
- Curate synthetic training trajectories from successful sub-graph traversals, intent classifications, and concept reorganization actions.
- Fine-tune local Ministral 3-8B model on Colab vLLM server to optimize structured graph actions (`CONNECT_DIRECT`, `CREATE_INTERMEDIATE`, `SPLIT_CONCEPT`) with zero-shot reliability.
- Expand Me-Mex beyond external memory into the core memory and context backbone of **Cortex-OS**.

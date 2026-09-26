# Graph-Memex (`me-mex`)

> **Agentic Knowledge Graph & Multi-Modal High-Volume Intake Engine**

Graph-Memex (`me-mex`) is an agentic research assistant and personal long-term memory system designed to digest massive streams of multi-modal content—including academic research papers, YouTube transcripts, lecture audio, codebase repositories, and experimental logs—without manual file scrolling or cognitive overload.

---

## 🏗️ The Operational System Architecture

Graph-Memex operates on a continuous **Retrieval $\rightarrow$ Exploration & Editing $\rightarrow$ Ingestion & Macro Update $\rightarrow$ Retrieval** loop:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        1. Multi-Modal Ingestion & Staging                              │
└────────────────────────────────────────────────────────────────────────────────────────┘
 - Staged Sandbox: Uploaded documents/links do NOT immediately populate the active graph.
 - Out-of-Graph Passage Storage: Text chunks are stored as plain text records in `passages`
   collection, linked only via `passage_pointers` inside atomic `CONCEPT` nodes.
 - Plain text retrieval: Passages are opened only when clicked to validate concept extraction.

┌────────────────────────────────────────────────────────────────────────────────────────┐
│                       2. Memory Storage & Clean 3-Element Topology                      │
└────────────────────────────────────────────────────────────────────────────────────────┘
 - Zero Passage Clutter: Passages are NOT graph nodes. The active network contains only:
     1. ROOT_MEDIA Nodes : Papers, Reports, Blogs, Transcripts, Code Repos.
     2. CONCEPT Nodes    : Self-evolving atomic notes with multi-attribute tags.
     3. CONNECTION_EDGE  : Qualitative relation edges (`BUILDS_UPON`, `CONTRASTS_WITH`, `SUPERSEDES`).
 - Historical Edge Decay: Superseded relations decay in weight from `1.0` down to `0.3`
   (`HISTORICAL_SUPERSEDED`), preserving history without cluttering path searches.

┌────────────────────────────────────────────────────────────────────────────────────────┐
│                     3. Dynamic Concept Hub Personas & Telemetry                        │
└────────────────────────────────────────────────────────────────────────────────────────┘
 - Dynamic Concept Hub Discovery: High-centrality concept nodes detected in real time (<5ms)
   via `rustworkx` eigenvector/degree centrality.
 - Concept Specialist Personas: Instantiated dynamically per hub node with adjacent subgraph context.
   Personas execute `duckduckgo_web_search` tool calls to retrieve live external evidence.
 - Real-Time SSE Telemetry: Streams persona traversal events (`traversing_node_ids`) to animate the
   WebGL canvas (`react-force-graph-2d`).

┌────────────────────────────────────────────────────────────────────────────────────────┐
│                      4. Agentic Tool Ingestion & Edge Evolution                        │
└────────────────────────────────────────────────────────────────────────────────────────┘
 - Tool-Based Ingestion: Executive Orchestrator calls `ingest_document_tool` when URLs/PDFs are pasted.
 - Out-of-Graph Passage Storage: Stores raw text chunks in `passages` collection.
 - Dynamic Edge Weight Decay: Superseded relations decay in weight (`1.0` -> `0.3`) without deleting history.
```

---

## 📚 Literature Synthesis & Paradigm Mapping

| Paper | Key Innovation | Role in Graph-Memex (`me-mex`) |
| :--- | :--- | :--- |
| **Microsoft GraphRAG** ([2404.16130](https://arxiv.org/abs/2404.16130)) | Hierarchical Leiden community detection & Map-Reduce QFS. | Department Macro Documents partitioning graph into 3–4 communities via NetworkX. |
| **OSU HippoRAG 2** ([2502.14802](https://arxiv.org/abs/2502.14802)) | Dual-node graph (Passages + Phrases) with joint vector-PPR search. | Out-of-graph passage pointers linked to concept nodes for single-hop factual verification. |
| **HKU LightRAG** ([2410.05779](https://arxiv.org/abs/2410.05779)) | Key-Value entity/relation profiling & dual-level retrieval. | High-speed streaming ingestion into MongoDB without global re-clustering. |
| **Zep Graphiti** ([2501.13956](https://arxiv.org/abs/2501.13956)) | Bi-temporal knowledge graph schema ($T_{\text{valid}}, T_{\text{trans}}$). | Edge weight decay (`1.0` $\rightarrow$ `0.3`) for superseded facts and historical papers. |
| **A-MEM** ([2502.12110](https://arxiv.org/abs/2502.12110)) | Zettelkasten atomic notes with retroactive memory evolution loops. | Atomic `CONCEPT` nodes that self-evolve summaries when new papers arrive. |
| **Cognee** ([2505.24478](https://arxiv.org/abs/2505.24478)) | Extract-Cognify-Load (ECL) pipeline with Pydantic structured output models. | Standardizes MongoDB engine models (`DocumentRecord`, `PassageRecord`, `GraphNodeRecord`, `ConnectionEdgeRecord`). |
| **PaperQA2** ([2409.13740](https://arxiv.org/abs/2409.13740)) | Reranking Contextual Summarization (RCS). | FastMCP tool filtering & plain text passage retrieval. |
| **Stanford STORM** ([2402.14207](https://arxiv.org/abs/2402.14207)) | Pre-writing perspective persona discovery & outline curation. | Color-coded Department Personas debating retrieval and ingestion deltas. |
| **Google Co-Scientist** ([2502.18864](https://arxiv.org/abs/2502.18864)) | Multi-agent tournament evolution & reflection loops. | Multi-persona integration debates evaluating graph evolution proposals. |
| **ScientistOne** ([2605.26340](https://arxiv.org/abs/2605.26340)) | Chain-of-Evidence (CoE) framework & integrity audit checks. | Hard-links every concept node back to raw document file paths and passage IDs. |

---

## 🛠️ Technology Stack & Engine Architecture

* **Database Engine:** **MongoDB** document database (`documents`, `passages`, `nodes`, `edges`, `macro_documents`, `staging_sandbox`) with in-memory fallback for local execution.
* **LLM Gateway:** **Ministral 3-8B** running remotely via Colab vLLM server (`http://localhost:8000/v1`) with local rule-based fallback.
* **Graph Analytics Worker:** **`rustworkx`** PyDiGraph for eigenvector/degree Hub Centrality ranking + **`NetworkX`** Louvain community partitioning.
* **Agent Protocol & Tools:** **FastMCP** (Python MCP SDK) exposing typed tools (`search_arxiv_papers`, `fetch_web_article`, `get_graph_nodes`, `get_passages_by_ids`, `get_macro_documents`, `calculate_hub_rankings`).
* **Search Integrations:** **`arxiv`** API client and **`trafilatura`** web page markdown extractor.
* **Telemetry Streaming:** **FastAPI + SSE Starlette** streaming real-time colored persona node traversal events to the WebGL canvas.
* **Frontend Visualization:** **React + WebGL** (`react-force-graph-2d`), featuring off-canvas Markdown drawers and visual node highlights.

---

## 🚀 Backend Implementation & Verification Status

The backend engine (`me-mex/backend`) is fully implemented and verified:

- ✅ **`app/db.py`**: MongoDB Database Engine with models for Documents, Passages, Graph Nodes, Connection Edges, Macro Documents, and Staging Records.
- ✅ **`app/services/llm_gateway.py`**: vLLM gateway client targeting Colab Ministral 3-8B with local rule-based fallback.
- ✅ **`app/services/graph_analytics.py`**: `rustworkx` Hub Centrality worker & `NetworkX` Louvain community partitioner.
- ✅ **`app/tools/search_tools.py`**: ArXiv research paper search and Trafilatura web article text extractor.
- ✅ **`app/agents/department_persona.py`**: Color-coded Department Personas for parallel graph exploration and ingestion debates.
- ✅ **`app/agents/orchestrator.py`**: Executive Orchestrator coordinating User Flow 1 (Ingestion) and User Flow 2 (Retrieval).
- ✅ **`app/api/sse.py`**: FastAPI SSE endpoints (`/api/sse/retrieval` & `/api/sse/ingestion`) streaming live persona traversal telemetry.
- ✅ **`app/mcp/server.py`**: FastMCP server exposing graph search, passage retrieval, and analytics tools.
- ✅ **`test_verification.py`**: Automated verification test suite passing all database, analytics, retrieval stream, and ingestion delta checks.

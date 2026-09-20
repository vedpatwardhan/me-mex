## GraphRAG: https://arxiv.org/pdf/2404.16130

### **Paper Metadata**
* **Title:** From Local to Global: A Graph RAG Approach to Query-Focused Summarization
* **Authors:** Darren Edge, Ha Trinh, Newman Cheng, Joshua Bradley, Alex Chao, Apurva Mody, Steven Truitt, Jonathan Larson (Microsoft Research)
* **ArXiv ID:** [2404.16130](https://arxiv.org/abs/2404.16130)

---

### **1. Core Motivation & Problem Addressed**
* **Standard RAG Bottleneck:** Traditional RAG retrieves top-$k$ text passages using vector similarity search. While effective for **explicit/local fact retrieval** (*"Who was the author of paper X?"*), it fails completely on **global sensemaking / Query-Focused Summarization (QFS)** (*"What are the main research themes in this dataset?"* or *"What are the key conflicts between these approaches?"*).
* **QFS Scalability Challenge:** Traditional QFS algorithms cannot scale to massive datasets (~1M+ tokens) due to computational overhead and context window limitations.
* **GraphRAG Solution:** Combines LLM-extracted Knowledge Graphs with hierarchical graph clustering algorithms to pre-summarize entire corpora at multiple semantic scales, enabling fast and comprehensive global answer synthesis.

---

### **2. Technical Architecture & 4-Stage Pipeline**

```
Source Documents 
     │
     ▼
[Stage 1: Text Chunking & Entity-Relation Extraction] 
     │ (LLM extracts Entities, Relations, & Claims)
     ▼
[Stage 2: Graph Construction & Leiden Community Detection] 
     │ (Hierarchical Partitioning into C3 -> C2 -> C1 -> C0 Clusters)
     ▼
[Stage 3: Pregenerated Community Summarization] 
     │ (LLM generates community report for every cluster)
     ▼
[Stage 4: Query Execution Engine]
   ├── Global Search: Map-Reduce over Community Summaries (Broad QFS queries)
   └── Local Search: Entity-Anchored Subgraph Traversal (Fact lookup queries)
```

#### **Stage 1: Text Chunking & Per-Chunk Local Extraction**
* Source text is divided into thousands of small chunks (e.g., 300–600 tokens).
* An LLM extracts domain entities (nodes), relationships (edges), and claims per chunk via Open Information Extraction (OpenIE) prompts.
* *Output:* Thousands of tiny, isolated subgraphs corresponding to each chunk.

#### **Stage 1.5: Global Graph Union & Node/Edge Merging (Crucial Bridge)**
* **Not Per-Chunk Clustering:** Community detection is **NOT** run on individual chunk graphs.
* **Node Merging (Deduplication):** All entity instances across chunks (e.g., `[Transformer]` mentioned in Chunks 1, 45, and 100) are merged into **a single canonical node** in the global graph.
* **Edge Aggregation:** When multiple chunks describe a connection between the same entity pair, a single edge is created whose **weight/strength is incremented** (weight = occurrence count/confidence), storing source chunk IDs as provenance.
* *Output:* **ONE single, unified global Knowledge Graph** representing the entire corpus.

#### **Stage 2: Hierarchical Community Detection (Leiden Algorithm)**
* The **Leiden Algorithm** (an optimized variant of Louvain from network science) runs on the **single global graph**.
* It partitions the network into a hierarchy of communities based on topology and edge weights:
  * **Level 0 (Root / Macro):** Broad overarching thematic domains (e.g., *Generative AI*).
  * **Level 1–2 (Meso):** Sub-topics and paradigm clusters (e.g., *Transformer Variants*, *World Models*).
  * **Level 3 (Micro):** Fine-grained entity clusters (e.g., *Attention Mechanisms*, *KV Caching*).

#### **Stage 3: Pregenerated Community Summarization**
* For every community cluster across all hierarchy levels, an LLM generates a structured **Community Report**.
* Reports contain a title, executive summary, key findings, and explicit entity/relationship references.
* Crucially, summarization happens **offline during indexing**, shifting the synthesis overhead away from query time.

#### **Stage 4: Query Execution (Global vs. Local Search)**
* **Global Search (Map-Reduce QFS):**
  1. User asks a broad question (*"What are the core failure modes across all models?"*).
  2. Community reports at a specified hierarchy level are sliced into context windows.
  3. Parallel **Map step**: Each community report generates an intermediate partial response + rating.
  4. **Reduce step**: Top partial responses are aggregated and synthesized into a final comprehensive answer.
* **Local Search (Entity-Anchored):**
  1. Vector search identifies seed entities matching the user query.
  2. Fanning-out retrieves adjacent entity nodes, relationships, and raw text chunks for targeted answer generation.

---

### **3. Implementation Details & Software Ecosystem**

#### **Microsoft GraphRAG Reference Implementation (`graphrag` package)**
Microsoft released an open-source Python package [`microsoft/graphrag`](https://github.com/microsoft/graphrag) that implements the pipeline:

| Component / Layer | Library / Engine Used | Implementation Mechanics |
| :--- | :--- | :--- |
| **Pipeline CLI / SDK** | `graphrag` Python Package | Entry point for indexing (`graphrag index`) and querying (`graphrag query`). |
| **Hierarchical Clustering** | `graspologic` | Uses Microsoft's `graspologic` Python library (built on C++ bindings for the **Leiden algorithm**) to compute hierarchical community partitions on the NetworkX/igraph graph. |
| **Graph Structure & Memory** | `networkx` / `igraph` | In-memory property graph representations storing nodes, edges, weights, and attributes during extraction and partitioning. |
| **Data Storage / Serialization** | `pyarrow` / `parquet` / `LanceDB` | Intermediate indexing artifacts (entities, relationships, text units, community reports) are stored as tabular Parquet files and embedded in LanceDB vector tables. |
| **LLM Orchestration & Prompts** | `openai` API / `fnllm` | Executes structured extraction and community report generation via OpenAI models (GPT-4/GPT-4o) using retry wrappers and token estimators (`tiktoken`). |

#### **How Graph-Memex Implements & Adapts These Components**
In the **Graph-Memex (`me-mex`)** architecture, we adopt and swap specific components to run locally without expensive OpenAI API costs or rigid Parquet files:

```
[Input: Papers / Transcripts / Notes]
                │
                ▼
  [Local Ministral 3 8B via vLLM / llama.cpp]
    (Constrained JSON Schema Extraction)
                │
                ▼
  [MongoDB Storage Layer (pymongo)]
   ├── nodes collection (Entities, Papers, Lessons)
   ├── edges collection (Typed relationships)
   └── $vectorSearch HNSW Indexes
                │
                ▼
  [Python In-Memory Graph Engine (rustworkx / NetworkX)]
   ├── Hierarchical Clustering (graspologic / leidenalg)
   └── Centrality & FSRS-DAG Topological Scheduling
                │
                ▼
  [FastMCP Server & React Graph UI]
   ├── Agent Tools (fastmcp Python SDK)
   └── Force-Directed UI (react-force-graph WebGL)
```

1. **Extraction Engine:** Replaces OpenAI GPT-4 with **Local Ministral 3 8B** running via `vLLM` or `llama-cpp-python`, enforced with Context-Free Grammars / JSON Schemas (`outlines` / `pydantic`).
2. **Graph Storage & Traversal:** Replaces static Parquet files with **MongoDB document collections** (`nodes`, `edges`, `themes`). Uses `$graphLookup` for shallow traversals ($\le 2$ hops) and native MongoDB `$vectorSearch` for semantic lookup.
3. **Graph Analytics & Clustering:** Loads MongoDB edges into **`rustworkx`** or **`NetworkX`** in Python memory for fast millisecond computation of Leiden communities (`graspologic` / `leidenalg`) and PageRank centrality.
4. **Agent & UI Integration:** Exposes graph tools to agent clients via **`fastmcp`** (FastMCP Python SDK) and renders visual graphs via **`react-force-graph`** (WebGL 2D/3D).

---

### **4. Evaluation & Key Findings**
* **Benchmark:** Evaluated against baseline RAG and Naive QFS over ~1M-token datasets (news transcripts, enterprise corpora).
* **Metrics:** Evaluated using LLM-as-a-Judge across **Comprehensiveness**, **Diversity**, **Empowerment**, and **Directness**.
* **Results:** GraphRAG achieved substantial improvements in **comprehensiveness** (covering all relevant sub-themes across the corpus) and **diversity** (spanning varied perspectives) compared to vector-only RAG.

---

### **5. Structural Limitations & Failure Modes**
* **Prohibitive Indexing Cost:** Generating triples and summarizing hundreds of hierarchical communities requires thousands of LLM API calls, making offline indexing expensive and slow.
* **Non-Incremental / Batch-Oriented:** Adding new documents destabilizes existing Leiden community boundaries, requiring partial or total re-clustering and re-summarization.
* **High Token Consumption during Global Map-Reduce:** Fan-out over dozens of community reports consumes significant prompt context during query execution.

---

### **6. Strategic Implications for Graph-Memex (`me-mex/SPEC.md` & Literature Review)**

#### **A. Mapping to Graph-Memex Node & Connection Taxonomy**
* **Entity-Relation Extraction $\rightarrow$ Core Unit (`deeper_read_notes.md` + `edges`):** GraphRAG's triple extraction provides the foundation for automatically generating **Paper**, **Insight**, and **Tool** nodes in Graph-Memex, alongside weighted `SIMILAR_TO`, `BUILDS_UPON`, and `USES_TOOL` edges.
* **Community Summaries $\rightarrow$ Reverse-Index Clustering (`overall_insights.md`):** GraphRAG's hierarchical community detection is the automated mathematical equivalent of MEMEX's manual category clusters in `overall_insights.md` (e.g., *VLA Decoupling*, *World Models*).

#### **B. Architectural Adaptations for Graph-Memex (Why Not Pure GraphRAG?)**
As highlighted in `docs/memex_literature_review.md` (Table 1), pure GraphRAG has major limits for interactive personal memory:
1. **Streaming & Incremental Ingestion:** Graph-Memex requires low-latency, real-time paper, media, and note intake. GraphRAG's batch Leiden clustering is too expensive. Therefore, Graph-Memex adopts a **hybrid ingestion model**:
   * Uses **LightRAG / Fast GraphRAG** principles (key-value entity profiling & seed PageRank) for fast incremental streaming into MongoDB.
   * Leverages **Local Ministral 3 8B** with JSON Schema decoding for cost-free, offline entity-relation extraction.
2. **Graph Storage in MongoDB (No Neo4j):**
   * GraphRAG's hierarchy maps to MongoDB's partitioned collection schema (`nodes`, `edges`, `themes`).
   * Shallow neighborhood traversals ($\le 2$ hops) use `$graphLookup`, while deep graph analytics (PageRank, cluster centrality) run in memory via Python (`rustworkx`/`networkx`).
3. **Dual-Density Edge Rendering & Visualization:**
   * GraphRAG's community hierarchy informs MEMEX's visual distinction between **Strong Mesh Edges** (paper-to-paper relationship density) and **Weak Structural Edges** (high-level topic umbrella nodes), preventing graph UI "hairball" clutter in `react-force-graph`.
4. **Topological Morning Review & Curriculum Mode:**
   * GraphRAG's global Map-Reduce QFS concepts inspire Graph-Memex's **Delta Briefing** (daily macro synthesis of ingested content), while FSRS-DAG scheduling drives topological micro-reviews.

---

## HippoRAG: https://arxiv.org/pdf/2405.14831

### **Paper Metadata**
* **Title:** HippoRAG: Neurobiologically Inspired Long-Term Memory for Large Language Models
* **Authors:** Bernal Jiménez Gutiérrez, Yiheng Shu, Yu Gu, Michihiro Yasunaga, Yu Su (Ohio State University)
* **ArXiv ID:** [2405.14831](https://arxiv.org/abs/2405.14831)
* **Code Repository:** [OSU-NLP-Group/HippoRAG](https://github.com/OSU-NLP-Group/HippoRAG)

---

### **1. Core Motivation & Neurobiological Paradigm**
* **Problem Addressed:** Standard RAG fails on **multi-hop associative reasoning** (*"Which university did the advisor of paper X's primary author attend?"*). Solving this previously required iterative, multi-turn LLM reasoning pipelines (e.g., IRCoT), which are slow, expensive, and accumulate hallucination errors across iterations.
* **Neurobiological Inspiration:** Based on **Hippocampal Indexing Theory** (Teyler & DiScenna, 1986) in cognitive neuroscience, which explains how mammalian brains store and retrieve long-term memory:
  * **Neocortex (Pre-trained LLM):** Houses broad parametric semantic knowledge and language comprehension.
  * **Hippocampus (External Knowledge Graph):** Serves as an associative index tracking specific episodic memories, entity relationships, and passage locations.
  * **Parahippocampal Cortex (Dense Retriever):** Maps incoming query cues onto initial hippocampal index seed nodes.

---

### **2. Technical Architecture & 3-Step Pipeline**

```
[Phase 1: Memory Formation (Offline Indexing)]
 Source Passages ──(OpenIE via LLM)──> Extracted Noun Phrases / Entities
                                       │
                                       ├── (Passage-to-Phrase Edges) ──> Link to Source Document
                                       └── (Phrase-to-Phrase Edges)  ──> Connect via Cosine Similarity / Co-occurrence
                                       │
                                       ▼
                         [Associative Memory Graph]

[Phase 2: Memory Recall (Online Personalized PageRank)]
 User Query ──(NER / LLM)──> Seed Entity Nodes
                                 │
                                 ▼ (Probability Mass Initialization)
                 Personalized PageRank (PPR) Traversal
                                 │ (Deterministic Matrix Iteration)
                                 ▼
                     Top Ranked Passage Nodes

[Phase 3: Generation]
 Top Passages + User Query ──(LLM)──> Multi-Hop Grounded Answer
```

#### **Stage 1: Memory Formation (Graph Construction)**
* **OpenIE Phrase Extraction:** Documents are split into passages. An LLM performs Open Information Extraction (OpenIE) to extract noun phrases and entity triples without rigid pre-defined schema constraints.
* **Dual-Edge Graph Construction:**
  1. **Passage-to-Phrase Edges:** Direct edges linking passage nodes to the phrase nodes contained within them.
  2. **Phrase-to-Phrase Edges:** Edges connecting phrase nodes based on semantic similarity (computed via dense embedding cosine similarity above a threshold $\tau$) and co-occurrence.

#### **Stage 2: Memory Recall via Personalized PageRank (PPR)**
* **Seed Entity Recognition:** The user's query is parsed to identify salient query entities (seed nodes).
* **Deterministic Probability Propagation (PPR):**
  * Probability mass vector $\mathbf{v}_0$ is initialized on the query seed nodes.
  * The **Personalized PageRank (PPR)** algorithm iterates over the graph adjacency matrix $\mathbf{M}$:
    $$\mathbf{p}^{(t+1)} = (1 - \alpha) \mathbf{M} \mathbf{p}^{(t)} + \alpha \mathbf{v}_0$$
  * Probability flows across phrase-to-phrase and phrase-to-passage edges, automatically traversing associative multi-hop paths without calling the LLM at every step.

#### **Stage 3: Passage Retrieval & Answer Generation**
* Passages accumulating the highest PPR probability values are selected as context and passed to the LLM for single-pass answer generation.

---

### **3. Implementation Details & Software Ecosystem**

#### **Official HippoRAG Reference Implementation (`OSU-NLP-Group/HippoRAG`)**

| Component / Layer | Library / Engine Used | Implementation Mechanics |
| :--- | :--- | :--- |
| **Pipeline Core** | Python / `hiprag` | Core framework orchestrating indexing, OpenIE extraction, PPR calculation, and evaluation loops. |
| **Graph & Matrix Engine** | `igraph` / `scipy.sparse` / `numpy` | Builds sparse adjacency matrices representing phrase-passage connectivity; computes PPR via fast, vectorized matrix-vector multiplications. |
| **Phrase Embeddings** | `sentence-transformers` / `Contriever` | Encodes noun phrases into dense vectors to calculate pairwise cosine similarity and build phrase-to-phrase similarity edges. |
| **Extraction & Seed NER** | `transformers` / `vllm` / `openai` | Runs LLM OpenIE prompts for offline indexing and query entity extraction during online retrieval. |

#### **How Graph-Memex Implements & Adapts HippoRAG**
1. **Real-Time Incremental Ingestion:** Unlike GraphRAG's expensive Leiden community re-clustering, HippoRAG's graph structure supports **instant incremental writes**. New papers, video transcripts, or notes simply add new phrase nodes and edges to MongoDB without re-indexing historical memory.
2. **Hybrid PPR + Spaced Repetition (FSRS):** In Graph-Memex, PPR is combined with the **Free Spaced Repetition Scheduler (FSRS)**. When generating morning review queues, candidate nodes are scored by combining their topological graph centrality (PPR) with their current memory decay (FSRS Retrievability).
3. **MongoDB + `scipy.sparse` Traversal:** Adjacency edges are stored in MongoDB's `edges` collection. For PPR execution, the active workspace graph is loaded into a scipy sparse matrix in Python memory, computing multi-hop retrievals in < 10ms.

---

### **4. Evaluation & Key Findings**
* **Benchmarks:** Evaluated on complex multi-hop QA datasets (**MuSiQue**, **2WikiMultiHopQA**, **HotpotQA**).
* **Performance Gain:** Outperforms standard RAG baselines by up to **+20%**.
* **Cost & Speed:** Achieves comparable or superior accuracy to multi-turn iterative retrieval (IRCoT) while being **10–30$\times$ cheaper** (fewer LLM prompt tokens) and **6–13$\times$ faster**.

---

### **5. Limitations & Evolutionary Upgrades (HippoRAG 2)**
* **Phrase Density Skew:** Uneven entity extraction can bias PPR probability mass toward passages containing high entity counts, even if semantically weak.
* **Evolution in HippoRAG 2:** The authors followed up with **HippoRAG 2**, introducing a **dual-node knowledge graph** containing both explicit phrase nodes and passage nodes connected via synonymy and contextual provenance edges, eliminating factual retrieval drop-offs.

---

### **6. GraphRAG vs. HippoRAG Architectural Matrix**

| Dimension | Microsoft GraphRAG | OSU HippoRAG |
| :--- | :--- | :--- |
| **Primary Goal** | **Global Sensemaking / QFS** (*"Summarize main themes across all docs"*) | **Multi-Hop Associative Recall** (*"Connect fact A to fact B across docs"*) |
| **Core Graph Primitive** | Entity-Relation Triples & Leiden Hierarchical Communities | Phrase & Passage Nodes connected by Co-occurrence & Embedding Similarity |
| **Graph Algorithm** | **Leiden Community Clustering** | **Personalized PageRank (PPR)** |
| **Retrieval Mechanism** | Map-Reduce over pregenerated Community Summaries | Seed node activation $\rightarrow$ PPR probability propagation |
| **Memory Updates** | Batch-oriented (requires re-clustering) | **Native Incremental Streaming** (fast node insertion) |
| **LLM Compute Cost** | High (expensive offline indexing + Map-Reduce context) | Low (one-pass OpenIE + fast PPR linear algebra) |

---

### **7. Strategic Implications for Graph-Memex (`me-mex/SPEC.md` & Literature Review)**
* **Primary Associative Retrieval Engine:** HippoRAG's PPR traversal forms the core mechanism for discovering implicit connections across papers, video transcripts, and experimental logs in Graph-Memex.
* **Low-Cost Ingestion Pipeline:** Allows MEMEX to accept high-volume multi-modal streams (YouTube transcripts, code logs) incrementally without breaking existing knowledge graphs.

---

## HippoRAG 2: https://arxiv.org/pdf/2502.14802

### **Paper Metadata**
* **Title:** From RAG to Memory: Non-Parametric Continual Learning for Large Language Models (HippoRAG 2)
* **Authors:** Bernal Jiménez Gutiérrez, Yu Gu, Yiheng Shu, Michihiro Yasunaga, Yu Su (Ohio State University - Feb 2025)
* **ArXiv ID:** [2502.14802](https://arxiv.org/abs/2502.14802)
* **Code Repository:** [OSU-NLP-Group/HippoRAG](https://github.com/OSU-NLP-Group/HippoRAG)

---

### **1. Core Motivation & Problem Addressed**
* **The "Factual Retrieval Drop-Off" in Graph RAG:** Early graph-augmented RAG systems (GraphRAG, HippoRAG 1) succeeded in multi-hop associative recall and global sense-making, but suffered an unintended **performance drop on basic single-hop factual queries** compared to standard dense vector RAG. This was caused by relying purely on extracted phrase nodes, which discarded raw passage-level semantic representations.
* **Non-Parametric Continual Learning Paradigm:** HippoRAG 2 reframes RAG as true **non-parametric continual memory**—allowing LLMs to continuously acquire, organize, and recall knowledge over time without parametric fine-tuning (avoiding catastrophic forgetting), while outperforming vector search across **all three memory dimensions**:
  1. **Factual Memory** (single-hop QA).
  2. **Associative Memory** (multi-hop relational reasoning).
  3. **Sense-Making Memory** (global QFS / thematic synthesis).

---

### **2. Technical Architecture & Key Innovations over HippoRAG 1**

```
 [Unified Dual-Node Knowledge Graph Schema]

  (Passage Node P1) ════════ Dense Similarity Edge ════════> (Passage Node P2)
        ║                                                          ║
   Provenance                                                 Provenance
        ║                                                          ║
        ▼                                                          ▼
  (Phrase Node E1) ──────── Synonymy / Similarity Edge ────> (Phrase Node E2)
```

#### **Innovation A: Dual-Node Graph Topology**
* HippoRAG 2 constructs a **Dual-Node Knowledge Graph** containing **both Passage Nodes (chunks) AND Phrase/Entity Nodes**.
* Connects the topology using **three explicit edge types**:
  1. **Passage-Phrase Edges (Provenance):** Links raw document passages to the entities extracted via OpenIE.
  2. **Phrase-Phrase Edges (Synonymy/Co-occurrence):** Connects entity nodes based on embedding cosine similarity and co-occurrence.
  3. **Passage-Passage Edges (Contextual Similarity):** Connects raw passage nodes directly to each other based on dense vector embedding similarity.

#### **Innovation B: Joint Vector-Graph PPR Initialization**
* Unlike HippoRAG 1 (which initialized PPR probability mass purely on phrase seed nodes), HippoRAG 2 places initial probability mass $\mathbf{v}_0$ **jointly across top dense vector retrieved passage nodes AND recognized phrase seed nodes**.
* This guarantees that single-hop factual queries leverage dense vector passage paths, while multi-hop queries traverse phrase-passage associative paths.

#### **Innovation C: Online LLM Recognition Filtering**
* Before running PPR, HippoRAG 2 uses a light online LLM pass to **filter and recognize salient query entities** and eliminate noisy/false-positive seed nodes, ensuring clean probability propagation.

---

### **3. Implementation Details & Software Ecosystem**

#### **Reference Implementation Details (`OSU-NLP-Group/HippoRAG`)**

| Component / Layer | Library / Engine Used | Implementation Mechanics |
| :--- | :--- | :--- |
| **Dual-Node Graph Engine** | `igraph` / `scipy.sparse` | Stores a unified sparse adjacency matrix encoding passage-passage, phrase-phrase, and passage-phrase edges. |
| **Dense Retriever Layer** | `faiss` / `sentence-transformers` | Executes dense vector searches over passage nodes to populate initial PPR probability mass vector $\mathbf{v}_0$. |
| **PPR Matrix Iteration** | `scipy.sparse` / `torch` | Runs joint Personalized PageRank iterations over the dual-node matrix, propagating probability mass across passage and phrase boundaries. |
| **LLM Recognition Filter** | `vllm` / `openai` | Filters candidate entities and formats retrieved passages into grounded context for answer generation. |

#### **How Graph-Memex Implements & Adapts HippoRAG 2**
* **Direct Schema Match in MongoDB:** Graph-Memex's database schema natively decouples **Passage-level nodes** (`PAPER`, `TRANSCRIPT`, `DEEP_LESSON`) and **Phrase-level nodes** (`INSIGHT`, `TOOL`), matching HippoRAG 2's dual-node graph 1-to-1.
* **Unified Retrieval Pipeline:** When a user queries Graph-Memex:
  1. Native MongoDB `$vectorSearch` retrieves candidate passage/paper nodes.
  2. Extracted query entities retrieve phrase nodes.
  3. Joint PPR runs over the combined adjacency matrix in Python memory, retrieving contextually rich and factually accurate nodes in < 15ms.

---

### **4. Evaluation & Key Findings**
* **Comprehensive Victory across All Memory Tasks:** HippoRAG 2 outperforms standard dense RAG, GraphRAG, and HippoRAG 1 across factual, associative, and sense-making benchmarks.
* **Associative Memory Benchmark:** Achieves a **+7% improvement** over state-of-the-art dense embedding models on multi-hop associative recall tasks.
* **Factual Memory Restoration:** Fully eliminates the factual QA drop-off suffered by HippoRAG 1 and GraphRAG.

---

### **5. Three-Way RAG Evolution Matrix**

| Feature | Microsoft GraphRAG | OSU HippoRAG 1 | OSU HippoRAG 2 |
| :--- | :--- | :--- | :--- |
| **Graph Topology** | Entity-Relation Triples | Phrase Nodes + Passage Links | **Dual-Node Graph (Passages + Phrases)** |
| **Edge Structure** | Weighted Relation Edges | Phrase-Phrase + Passage-Phrase | **Passage-Passage + Phrase-Phrase + Provenance Edges** |
| **Graph Algorithm** | Leiden Community Detection | Phrase-based PPR | **Joint Vector-Graph PPR** |
| **Factual Single-Hop QA** | Weak | Weak | **State-of-the-Art (Matches/Beats Vector RAG)** |
| **Multi-Hop QA** | Moderate | Excellent | **State-of-the-Art (+7% Over Dense Embeddings)** |
| **Global Sense-Making** | Excellent | Good | **Excellent** |
| **Continual Memory Writes** | Expensive Batch Re-clustering | Fast Incremental Insertion | **Fast Non-Parametric Incremental Writes** |

---

### **6. Strategic Implications for Graph-Memex (`me-mex/SPEC.md` & Literature Review)**
* **Architectural Blueprint for MEMEX Retrieval Engine:** HippoRAG 2 provides the final architectural solution for Graph-Memex's backend. By combining MongoDB `$vectorSearch` (passage-passage similarity) with dual-node PPR traversal (phrase-insight links), MEMEX achieves single-hop factual precision, multi-hop paper synthesis, and low-latency incremental memory updates.

---

## LightRAG: https://arxiv.org/pdf/2410.05779

### **Paper Metadata**
* **Title:** LightRAG: Simple and Fast Retrieval-Augmented Generation
* **Authors:** Zirui Guo, Liang Zhao, Zhiruo Zhou, Guifeng Wang, Yilong Zhao, Wei Zhang (HKU Data Intelligence Lab - Oct 2024)
* **ArXiv ID:** [2410.05779](https://arxiv.org/abs/2410.05779)
* **Code Repository:** [HKUDS/LightRAG](https://github.com/HKUDS/LightRAG)

---

### **1. Core Motivation & Problem Addressed**
* **The Cost & Incremental Update Bottleneck of GraphRAG:** While Microsoft GraphRAG enables global sense-making via Leiden community detection, it suffers from **prohibitive indexing costs** (thousands of LLM calls for community reports) and **cannot support real-time incremental updates**. Adding a single new document destabilizes existing communities and requires partial/full re-clustering.
* **LightRAG Solution:** LightRAG introduces a lightweight, fast graph-augmented RAG framework that provides **dual-level retrieval** (low-level entity facts + high-level conceptual themes) while enabling **native, low-cost incremental updates** without global re-indexing.

---

### **2. Technical Architecture & Dual-Level Retrieval**

```
 [Raw Document Chunks]
           │
           ▼
 [LLM Entity & Relationship Extraction]
           │
           ▼
 [Graph Construction & KV Profiling]
   ├── Entity Nodes (Name, Type, Description)
   └── Relationship Edges (Source, Target, Context Keywords, Description)
           │
           ├───────────────────────────────┐
           ▼                               ▼
 [Low-Level Retrieval]           [High-Level Retrieval]
 (Specific Entity/Edge Facts)   (Broad Conceptual Relation Themes)
           │                               │
           └───────────────┬───────────────┘
                           ▼
               [Hybrid Context Fusion]
                           │
                           ▼
                [LLM Answer Generation]
```

#### **A. Dual-Level Indexing (Graph + Key-Value Profiling)**
* Text chunks are processed by an LLM to extract entities and relationship triples.
* Extracted elements are stored in a **Key-Value (KV) Storage Structure**:
  * **Entity Profiles:** Key = Entity Name; Value = LLM-generated description & context snippets.
  * **Relationship Profiles:** Key = `(Source, Target)`; Value = Summary of relationship context and key themes.

#### **B. Dual-Level Retrieval Paradigm**
* **Low-Level Retrieval:** Targeted at specific entity queries (*"What are the parameters of Model X?"*). Retrieves specific entity nodes and direct edge descriptions.
* **High-Level Retrieval:** Targeted at broad, abstract queries (*"How do flow matching methods compare to diffusion policies?"*). Retrieves high-level conceptual relationship themes spanning multiple entities.
* **Hybrid Retrieval Mode:** Automatically executes low-level and high-level retrieval in parallel, fusing entity facts and broad thematic contexts into a unified prompt for answer generation.

#### **C. Fast Incremental Update Algorithm**
1. When a new text chunk is ingested, LightRAG extracts new entities and relationships.
2. New nodes and edges are merged directly into the existing graph via KV deduplication.
3. **No Global Re-Clustering:** Unlike GraphRAG, LightRAG avoids Leiden community detection and pregenerated reports, allowing new documents to be indexed in seconds at minimal token cost.

---

### **3. Implementation Details & Software Ecosystem**

#### **Official Reference Implementation (`HKUDS/LightRAG`)**

| Component / Layer | Library / Engine Used | Implementation Mechanics |
| :--- | :--- | :--- |
| **Python Package** | `lightrag-hku` (`pip install lightrag-hku`) | Core pipeline managing async chunk ingestion, graph construction, and dual-level query routing. |
| **Graph Storage Backend** | `NetworkX` / `Neo4j` / `MongoDB` | Property graph representation storing entities, relations, and adjacency lists. |
| **Key-Value & Vector Store** | `JsonKVStorage` / `NanoVectorDB` / `Oracle` | Stores entity/relationship profiles and dense vectors for fast keyword and semantic lookup. |
| **LLM & Embedding Binding** | `openai` / `ollama` / `vllm` / `huggingface` | Supports plug-and-play LLM providers for extraction and answer synthesis. |

#### **How Graph-Memex Implements & Adapts LightRAG**
* **Fast Incremental Intake Pipeline:** MEMEX adopts LightRAG's incremental update strategy as its primary intake engine for daily arXiv papers, YouTube transcripts, and Markdown notes.
* **Dual-Level Ingestion into MongoDB:**
  * **Low-Level Entities** map to MEMEX `PAPER` and `TOOL` nodes.
  * **High-Level Conceptual Themes** map to MEMEX `INSIGHT` nodes (`overall_insights.md`).
* **Token Cost Efficiency:** By eliminating GraphRAG's offline Leiden report generation, MEMEX keeps ingestion costs near-zero using **Local Ministral 3 8B**.

---

### **4. Evaluation & Key Findings**
* **Token & Speed Efficiency:** Reduces indexing token expenditure by **up to 99%** compared to Microsoft GraphRAG while indexing in seconds.
* **Retrieval & Answer Quality:** Outperforms standard vector RAG and baseline GraphRAG on both specific factual QA and high-level multi-document summarization benchmarks.

---

### **5. Comprehensive Graph RAG Taxonomy & Trade-off Matrix**

The table below highlights that **no single framework dominates all dimensions**: LightRAG is the winner for fast, low-cost ingestion, while HippoRAG 2 is the winner for deep multi-hop reasoning and factual recall.

| Capability / Metric | Microsoft GraphRAG | OSU HippoRAG 2 | HKU LightRAG |
| :--- | :--- | :--- | :--- |
| **Primary Specialty** | Global Sense-Making & QFS | **Deep Multi-Hop Associative Recall** | **Low-Cost Incremental Ingestion** |
| **Graph Primitive** | Hierarchical Leiden Clusters | **Dual-Node Graph (Passages + Phrases)** | Entity/Relation Key-Value Profiles + Graph |
| **Core Retrieval Algorithm** | Map-Reduce over Community Reports | **Joint Vector-Graph Personalized PageRank** | Dual-Level (Low-Level Entity + High-Level Theme) KV Search |
| **Multi-Hop Associative Traversal** | 🟡 Moderate (Cluster-level) | 🟢 **Best / Deepest (SOTA +7% via PPR)** | 🟡 **Shallow / Basic** (1-to-2 Hop KV Lookups) |
| **Single-Hop Factual Precision** | 🔴 Weak (Abstraction loss) | 🟢 **Best / SOTA** (Dual-node restores vector precision) | 🟢 **High** (Direct entity KV lookups) |
| **Global Macro Summarization** | 🟢 **Best** (Exhaustive Leiden reports) | 🟡 Good (PPR cluster aggregation) | 🟡 Good (High-level relation theme routing) |
| **Indexing Token Overhead** | 🔴 **Extremely High** (Thousands of LLM calls) | 🟡 **Moderate** (OpenIE + Embeddings) | 🟢 **Lowest / Cheapest** (Near-zero extra tokens) |
| **Incremental Updates** | 🔴 Batch Only (Requires re-clustering) | 🟢 **Native / Instant** | 🟢 **Native / Instant** |
| **Role in Graph-Memex (`me-mex`)** | **Daily Macro Delta Briefing** | **Deep Retrieval & Memory Review Engine** | **High-Volume Ingestion Pipeline** |

---

### **6. Strategic Implications for Graph-Memex (`me-mex/SPEC.md` & Literature Review)**

#### **A. Why LightRAG is NOT a Complete Replacement for HippoRAG 2**
* **Traversal Bottleneck:** LightRAG uses simple key-value lookups over 1-hop or 2-hop entity/relationship profiles. It **cannot run graph algorithms like Personalized PageRank (PPR)** to discover deep, multi-step associative paths across disparate documents.
* **Why HippoRAG 2 is Essential for Reasoning:** For complex research queries (*"Connect author A's world model to benchmark B's policy"*), HippoRAG 2's PageRank matrix iteration is strictly superior because it propagates probability mass dynamically across multi-edge paths.

#### **B. The Graph-Memex Hybrid Architecture**
Graph-Memex combines the distinct superpowers of both systems into a unified pipeline:

```
                      ┌───────────────────────────────────────────────┐
                      │ High-Volume Data Stream                       │
                      │ (arXiv PDFs, YouTube Transcripts, Notes)      │
                      └───────────────────────┬───────────────────────┘
                                              │
                                              ▼
                    [LIGHTRAG INGESTION MODEL]
                    - Low-cost OpenIE & Key-Value Profiling
                    - Instant incremental writes into MongoDB
                    - No expensive Leiden re-clustering
                                              │
                                              ▼
                    [MONGODB HYBRID STORE]
                    - Passage Nodes + Entity/Phrase Nodes
                    - Adjacency Matrix + $vectorSearch HNSW
                                              │
                                              ▼
                    [HIPPORAG 2 RETRIEVAL ENGINE]
                    - Joint Vector-Graph Personalized PageRank (PPR)
                    - Deep multi-hop associative paper synthesis
                    - FSRS-DAG morning review score calculation
```

1. **LightRAG powers INGESTION:** Manages high-speed, low-cost document chunking, entity profiling, and streaming updates into MongoDB.
2. **HippoRAG 2 powers RETRIEVAL & REVIEW:** Executes joint vector-graph PPR traversals over MongoDB data to answer complex multi-hop queries and drive the topological morning review queue.
3. **GraphRAG powers MACRO BRIEFINGS:** Pregenerates high-level community summaries for broad periodic workspace briefings.

---

## Zep / Graphiti: https://arxiv.org/pdf/2501.13956

### **Paper Metadata**
* **Title:** Zep: A Temporal Knowledge Graph Architecture for Agent Memory
* **Authors:** Daniel Chalef et al. (Zep AI - Jan 2025)
* **ArXiv ID:** [2501.13956](https://arxiv.org/abs/2501.13956)
* **Code Repository:** [getzep/graphiti](https://github.com/getzep/graphiti)

---

### **1. Core Motivation & Problem Addressed**
* **The Static Knowledge Assumption in RAG:** Existing Graph RAG frameworks (GraphRAG, LightRAG, HippoRAG) treat document collections as **static knowledge**. They assume facts are immutable and never contradict each other over time.
* **The Contradiction Dilemma in Agent Memory:** In real-world applications, AI agents interact with dynamic data streams (conversations, user preferences, evolving research benchmarks, software logs). When new information contradicts old knowledge (e.g., *"Model A was SOTA in 2024"* vs *"Model B surpassed Model A in 2025"*), standard RAG either destructively overwrites old facts (losing context) or retrieves both contradictory passages simultaneously, causing LLM hallucinations.
* **Zep / Graphiti Solution:** Introduces **Graphiti**, a **temporally-aware knowledge graph engine** that tracks time-dependent relationships using a **bi-temporal schema**. It invalidates obsolete facts without deleting them, enabling accurate current-state recall alongside historical "time-travel" reasoning.

---

### **2. Technical Architecture & Bi-Temporal Schema**

```
 [Raw Dynamic Episode / Chat / Log Stream]
                    │
                    ▼
       [Graphiti Extraction Engine]
                    │
                    ▼
      [Bi-Temporal Edge Construction]
   ├── Valid Time (T_valid): [valid_from, valid_to]  <-- Real-world validity range
   └── Transaction Time (T_transaction): timestamp   <-- System observation time
                    │
                    ▼
 [Fact Invalidation (Non-Destructive Overwrite)]
   - Old Fact Edge:  valid_to set to current timestamp (Closed / Invalidated)
   - New Fact Edge:  valid_from set to current timestamp (Active)
                    │
                    ▼
 [Hybrid Retrieval Engine: Vector + Keyword + Temporal Filter]
```

#### **A. Bi-Temporal Edge Schema**
Graphiti records two distinct temporal axes for every entity relationship edge:
1. **Valid Time ($T_{valid}$):** $\left[t_{\text{valid\_start}}, t_{\text{valid\_end}}\right]$ — The real-world timeframe during which the statement was true.
2. **Transaction Time ($T_{\text{transaction}}$):** $t_{\text{observed}}$ — The exact timestamp when the agent/system ingested the event.

#### **B. Non-Destructive Fact Invalidation**
* When a new episode contradicts an existing edge (e.g., a paper demonstrating that a previous assumption no longer holds), Graphiti **does NOT delete the old edge**.
* Instead, it sets $t_{\text{valid\_end}} = t_{\text{current}}$ on the historical edge and creates a new edge with $t_{\text{valid\_start}} = t_{\text{current}}$.
* **Result:** Current queries retrieve only active edges ($t_{\text{valid\_end}} = \text{null}$), while historical queries (*"What was the SOTA approach in 2023?"*) can filter by time range to reconstruct historical states accurately.

#### **C. Hybrid Temporal-Semantic Retrieval Engine**
Combines three retrieval signals in parallel:
1. **Dense Vector Search:** Matches query semantic intent against entity/passage embeddings.
2. **BM25 Keyword Search:** Captures exact entity and technical term occurrences.
3. **Temporal Edge Filtering:** Restricts candidate graph paths to edges valid at the query's target time point.

---

### **3. Implementation Details & Software Ecosystem**

#### **Official Reference Implementation (`getzep/graphiti`)**

| Component / Layer | Library / Engine Used | Implementation Mechanics |
| :--- | :--- | :--- |
| **Graph Engine Core** | Python / `graphiti-core` | Open-source Python library managing episode ingestion, entity resolution, bi-temporal edge tracking, and search. |
| **Backend Database** | Neo4j / FalkorDB / PostgreSQL (`pgvector`) / MongoDB | Storage layer supporting bi-temporal property graph edges and dense vector indexes. |
| **LLM & Extraction** | `openai` / `anthropic` / Local vLLM | Asynchronous background LLM workers performing entity extraction, coreference resolution, and contradiction detection. |

#### **How Graph-Memex Implements & Adapts Graphiti**
* **Bi-Temporal Schema in MongoDB:** MEMEX adds `valid_from`, `valid_to`, and `transaction_time` fields to its MongoDB `edges` collection.
* **Handling Evolving Research & Experiments:** Research paradigms and experimental logs evolve. When a new paper invalidates an older benchmark claim, MEMEX sets `valid_to` on the old edge. This prevents the morning review engine from presenting conflicting or obsolete claims as active truth.

---

### **4. Evaluation & Key Findings**
* **Deep Memory Retrieval (DMR) Benchmark:** Outperforms MemGPT (94.8% vs 93.4% accuracy).
* **LongMemEval Benchmark:** Achieves up to **+18.5% accuracy gain** on complex temporal reasoning tasks over long-term agent contexts while **reducing response latency by 90%**.

---

### **5. Master 4-Way Graph RAG Taxonomy Comparison Table**

| Feature | Microsoft GraphRAG | OSU HippoRAG 2 | HKU LightRAG | Zep Graphiti |
| :--- | :--- | :--- | :--- | :--- |
| **Primary Specialty** | Global QFS & Sense-Making | **Deep Multi-Hop Recall** | **Low-Cost Ingestion** | **Temporal Agent Memory** |
| **Graph Primitive** | Hierarchical Communities | Dual-Node Graph | Key-Value Entity Profiles | **Bi-Temporal Graph** |
| **Core Search** | Map-Reduce Summaries | Joint Vector-Graph PPR | Dual-Level KV Search | **Vector + Keyword + Temporal Filter** |
| **Temporal Aware** | ❌ Static | ❌ Static | ❌ Static | 🟢 **Bi-Temporal ($T_{valid}, T_{trans}$)** |
| **Fact Invalidation** | ❌ None | ❌ None | ❌ None | 🟢 **Non-Destructive Invalidation** |
| **Incremental Writes**| 🔴 Prohibitive | 🟢 Native | 🟢 Native | 🟢 **Native Streaming** |
| **MEMEX Role** | Macro Briefings | Retrieval & Review Engine | High-Volume Ingestion | **Temporal Log & Memory Sync** |

---

### **6. Strategic Implications for Graph-Memex (`me-mex/SPEC.md` & Literature Review)**
* **Temporal Lineage for Research Notes:** Integrates bi-temporal metadata into MEMEX's core unit (`deeper_read_notes.md`, `overall_insights.md`), ensuring that historical paper insights and experimental logs retain complete temporal provenance without corrupting current active knowledge.

---

## fastbmRAG: https://arxiv.org/pdf/2511.10014

### **Paper Metadata**
* **Title:** fastbmRAG: A Fast Graph-Based RAG Framework for Efficient Processing of Large-Scale Biomedical Literature
* **Authors:** G. Meng et al.
* **ArXiv ID:** [2511.10014](https://arxiv.org/abs/2511.10014)
* **Code Repository:** [menggf/fastbmRAG](https://github.com/menggf/fastbmRAG)

---

### **1. Core Motivation & Problem Addressed**
* **The Full-Text Graph Extraction Bottleneck:** Scientific literature (papers, technical reports) contains long, dense passages. Running unconstrained LLM graph extraction over full-text documents is computationally expensive, highly redundant, and generates overly dense, noisy graphs.
* **fastbmRAG Solution:** Exploits the natural structural hierarchy of scientific documents by introducing a **Two-Stage Draft-and-Refine Paradigm**. It builds a clean baseline graph from paper abstracts first, then uses vector entity linking to ground main-text details without redundant extraction—achieving a **>10$\times$ indexing speedup**.

---

### **2. Technical Architecture & Two-Stage Paradigm**

```
 [Academic / Technical Literature Corpus]
                    │
                    ├───────────────────────────────────────┐
                    ▼                                       ▼
  [Stage 1: Abstract-Level Graph Drafting]       [Stage 2: Main-Text Processing]
  - Extracts core high-signal entities & edges   - Parses full body text
  - Creates sparse "Skeleton Knowledge Graph"    - Uses Vector Entity Linking to
                    │                              ground main text to Draft Graph
                    └───────────────────┬───────────────────┘
                                        ▼
                         [Refined Knowledge Graph]
```

#### **Stage 1: Abstract-Level Graph Drafting**
* Paper abstracts contain concentrated summaries of core findings, key models, and primary contributions.
* fastbmRAG runs LLM extraction **only on abstracts** first, creating a concise, high-signal "Skeleton Knowledge Graph" of core entities and relationships.

#### **Stage 2: Main-Text Graph Refining via Vector Entity Linking**
* Instead of running costly unconstrained LLM extraction on main body text, main-text passages are embedded into vector space.
* **Vector Entity Linking:** Main-text mentions are grounded directly onto existing nodes and edges in the abstract-draft graph. Only genuinely novel entities absent from the abstract are added.
* **Result:** Eliminates node duplication and redundant LLM extraction passes, reducing indexing time by over 90%.

---

### **3. Implementation Details & Software Ecosystem**

#### **Official Reference Implementation (`menggf/fastbmRAG`)**

| Component / Layer | Library / Engine Used | Implementation Mechanics |
| :--- | :--- | :--- |
| **Pipeline Framework** | Python / `fastbmRAG` | Manages abstract parsing, graph drafting, and main-text entity linking. |
| **Entity Linking Layer** | PyTorch / `transformers` / Vector DB | Uses dense embeddings (Chroma / FAISS) to perform fast vector entity linking between main-text passages and abstract nodes. |
| **Graph Store** | NetworkX / igraph | Stores the draft and refined knowledge graph. |

#### **How Graph-Memex Implements & Adapts fastbmRAG**
* **Direct Match with MEMEX Two-Tiered Workflow:**
  * MEMEX paper entries start as short 2-line summaries / abstracts in `deeper_read_notes.md` (**Stage 1: Abstract Draft Node**).
  * When a paper receives a deep dive in `select_papers.md`, MEMEX applies fastbmRAG's **Vector Entity Linking** to attach detailed notes to the existing draft node without creating redundant graph nodes.

---

### **4. Evaluation & Key Findings**
* **Indexing Speedup:** Over **10$\times$ faster** graph indexing compared to conventional Graph-RAG frameworks.
* **Graph Quality:** Achieves superior entity precision and coverage by filtering out main-text noise.

---

### **5. Master 5-Way Graph RAG Taxonomy Comparison Table**

| Feature | Microsoft GraphRAG | OSU HippoRAG 2 | HKU LightRAG | Zep Graphiti | fastbmRAG |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Primary Focus** | Global QFS | **Deep Recall** | **Low-Cost Ingestion** | **Temporal Memory** | **Fast Literature Indexing** |
| **Graph Primitive** | Leiden Clusters | Dual-Node Graph | Key-Value Profiles | Bi-Temporal Graph | **Draft-and-Refine Graph** |
| **Core Mechanism** | Map-Reduce | Joint Vector PPR | Dual-Level KV | Temporal Filtering | **Vector Entity Linking** |
| **Indexing Speed**| 🔴 Slowest | 🟡 Moderate | 🟢 Fast | 🟢 Fast | 🟢 **Fastest (>10x)** |
| **MEMEX Role** | Macro Briefings | Review Engine | Multi-Modal Intake | Temporal Sync | **Paper Note Pipeline** |

---

### **6. Strategic Implications for Graph-Memex (`me-mex/SPEC.md` & Literature Review)**
* **Abstract-First Ingestion Pattern:** Standardizes how MEMEX processes academic papers: ingest abstracts into `deeper_read_notes.md` first for instant graph drafting, then refine via vector entity linking when detailed notes are added to `select_papers.md`.

---

## A-MEM: https://arxiv.org/pdf/2502.12110

### **Paper Metadata**
* **Title:** A-MEM: Agentic Memory for LLM Agents
* **Authors:** Wujiang Xu et al. (Feb 2025)
* **ArXiv ID:** [2502.12110](https://arxiv.org/abs/2502.12110)
* **Code Repositories:** [WujiangXu/A-mem](https://github.com/WujiangXu/A-mem) & [WujiangXu/A-mem-sys](https://github.com/WujiangXu/A-mem-sys)

---

### **1. Core Motivation & Zettelkasten Methodology**
* **The Static Memory Bottleneck:** Existing agent memory systems rely on rigid, pre-defined storage schemas or simple vector stores that cannot dynamically adapt to changing task requirements or evolving domain knowledge.
* **Zettelkasten Inspiration:** Based on **Niklas Luhmann's Zettelkasten (slip-box)** note-taking methodology, A-MEM organizes agent memory into an interconnected network of atomic, self-contained notes with rich structured attributes, dynamic link generation, and retroactive memory evolution.

---

### **2. Technical Architecture & 3-Step Lifecycle**

```
 [New Event / Paper / Experience Ingested]
                    │
                    ▼
 [Stage 1: Atomic Note Generation]
   - Structured JSON Note: Summary, Context Description, Keywords, Domain Tags, Vector Embedding
                    │
                    ▼
 [Stage 2: Agentic Dynamic Link Generation]
   - Candidate Search (Vector Similarity + Tag Matching)
   - LLM Agent evaluates relationships and creates explicit links (SIMILAR_TO, BUILDS_UPON, etc.)
                    │
                    ▼
 [Stage 3: Retroactive Memory Evolution]
   - Background Agent pass updates historical notes' context, tags, and links as domain context grows
```

#### **Stage 1: Atomic Note Generation**
When a new memory item is ingested, A-MEM creates a structured atomic note containing:
* `note_id`: Unique identifier.
* `content_summary`: Concise factual synthesis.
* `contextual_description`: Rich situational context.
* `keywords` & `domain_tags`: Structured classification attributes.
* `dense_embedding`: Vector representation for semantic search.

#### **Stage 2: Agentic Dynamic Link Generation**
* A-MEM executes a candidate search against existing notes using vector similarity and tag overlap.
* An LLM agent analyzes the candidate neighbors and explicitly generates directed relationship links (`SIMILAR_TO`, `BUILDS_UPON`, `CONTRASTS_WITH`, `PREREQUISITE`) with rationale justifications.

#### **Stage 3: Retroactive Memory Evolution**
* Crucially, memory organization in A-MEM is **not static after creation**.
* When a new note is added, it can trigger a background agent pass that **retroactively updates historical notes**—refining their context descriptions, updating their domain tags, or establishing new links to reflect the agent's expanding cumulative understanding.

---

### **3. Implementation Details & Software Ecosystem**

#### **Official Reference Implementation (`WujiangXu/A-mem-sys`)**

| Component / Layer | Library / Engine Used | Implementation Mechanics |
| :--- | :--- | :--- |
| **Memory System Core** | Python / `A-mem-sys` | Framework managing atomic note creation, link generation, and retroactive evolution loops. |
| **Vector & Attribute Index** | Vector DB / JSON Storage | Multi-attribute indexing combining dense vector embeddings with metadata tag filtering. |
| **Agentic Controller** | OpenAI API / Local LLM | Prompt-driven agent executing link generation decisions and memory evolution passes. |

#### **How Graph-Memex Implements & Adapts A-MEM**
* **Atomic Zettelkasten Notes:** MEMEX's MongoDB `nodes` collection natively maps to A-MEM atomic notes (storing `short_summary`, `context_description`, `tags`, `embedding`, and `fsrs_state`).
* **Agentic Memory Evolution Loop:** Inspired directly by A-MEM Stage 3, when a user ingests new paper notes, MEMEX runs an asynchronous background agent that proposes new similarity links and retroactively updates topic category takeaways in `overall_insights.md`.

---

### **4. Evaluation & Key Findings**
* **Empirical Validation:** Tested across 6 major foundation models, outperforming state-of-the-art memory baselines (MemGPT, baseline RAG).
* **Adaptability:** Demonstrates superior performance on long-term context tracking and adaptive task execution.

---

### **5. Master 6-Way Graph RAG Taxonomy Comparison Table**

| Feature | Microsoft GraphRAG | OSU HippoRAG 2 | HKU LightRAG | Zep Graphiti | fastbmRAG | A-MEM |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Primary Focus** | Global QFS | **Deep Recall** | **Low-Cost Ingestion** | **Temporal Memory** | **Fast Literature** | **Self-Evolving Memory** |
| **Graph Primitive** | Leiden Clusters | Dual-Node Graph | Key-Value Profiles | Bi-Temporal Graph | Draft-and-Refine | **Zettelkasten Atomic Notes** |
| **Core Mechanism** | Map-Reduce | Joint Vector PPR | Dual-Level KV | Temporal Filtering | Vector Entity Linking | **Agent Link & Evolution** |
| **Memory Evolution**| ❌ Static | ❌ Static | ❌ Static | 🟢 Fact Invalidation | ❌ Static | 🟢 **Retroactive Note Evolution** |
| **MEMEX Role** | Macro Briefings | Review Engine | Multi-Modal Intake | Temporal Sync | Paper Pipeline | **Proactive Link & Note Evolution** |

---

### **6. Strategic Implications for Graph-Memex (`me-mex/SPEC.md` & Literature Review)**
* **Zettelkasten Foundation:** Validates MEMEX's core design—treating papers, insights, and tools as atomic, interconnected Zettelkasten notes that evolve dynamically as new papers are read.

---

## Cognee: https://arxiv.org/pdf/2505.24478

### **Paper Metadata**
* **Title:** Optimizing the Interface Between Knowledge Graphs and LLMs for Complex Reasoning (Cognee)
* **Authors:** Boris Spasić, Vesna Pop-Dimitrijoska, et al. (Cognee AI - May 2025)
* **ArXiv ID:** [2505.24478](https://arxiv.org/abs/2505.24478)
* **Code Repository:** [cognee-ai/cognee](https://github.com/cognee-ai/cognee)

---

### **1. Core Motivation & Problem Addressed**
* **Unoptimized Graph-LLM Interfaces:** Integrating Large Language Models with Knowledge Graphs introduces complex multi-layer configurations—such as chunking boundaries, entity extraction prompts, ontology definitions, retrieval search strategies, and prompt formatting. Most RAG systems rely on static, un-tuned default parameters, leading to brittle performance across complex reasoning tasks.
* **Cognee Solution:** Introduces **Cognee**, a modular **Extract-Cognify-Load (ECL)** framework for end-to-end knowledge graph construction and hybrid retrieval, accompanied by systematic hyperparameter optimization across 14+ graph-vector search strategies.

---

### **2. Technical Architecture & ECL Pipeline**

```
 [Heterogeneous Input Documents / Transcripts]
                      │
                      ▼
            [Extract Stage (Parsing)]
   - Code-based & PDF chunking with metadata tagging
                      │
                      ▼
            [Cognify Stage (Structuring)]
   - Pydantic / BAML Structured LLM Extraction
   - Ontology grounding & entity disambiguation
   - Dense vector embedding generation
                      │
                      ▼
            [Load Stage (Multi-Engine Storage)]
   - Persists data across Relational + Vector + Graph stores
                      │
                      ▼
        [Hybrid Retrieval & Re-ranking Engine]
   - Evaluates 14+ retrieval configurations (Vector + Graph Hop + Re-ranking)
```

#### **Stage 1: Extract (Parsing & Chunking)**
* Ingests heterogeneous source files (PDFs, Markdown, transcripts) and partitions them using typed, context-aware chunking rules.

#### **Stage 2: Cognify (Structuring & Graph Building)**
* Applies **Pydantic / BAML structured outputs** to extract entities and relationships strictly aligned with domain ontologies.
* Generates dense vector embeddings for nodes and passages while grounding canonical entity nodes to avoid duplication.

#### **Stage 3: Load (Multi-Engine Persistence)**
* Decouples data storage across three specialized engines:
  1. **Relational Layer:** Tracks document metadata and task state.
  2. **Vector Layer:** Manages HNSW embeddings for semantic similarity.
  3. **Graph Layer:** Stores labeled property graph topology for multi-hop traversal.

#### **Stage 4: Modular Hybrid Retrieval**
* Evaluates 14+ hybrid retrieval strategies combining dense vector search, graph expansion ($k$-hop neighborhood fanning), and cross-encoder re-ranking.

---

### **3. Implementation Details & Software Ecosystem**

#### **Official Reference Implementation (`cognee-ai/cognee`)**

| Component / Layer | Library / Engine Used | Implementation Mechanics |
| :--- | :--- | :--- |
| **Framework Core** | Python / `cognee` (`pip install cognee`) | Modular pipeline orchestrating Extract, Cognify, Load, and Search workflows. |
| **Structured LLM Extraction** | Pydantic / BAML | Constrains LLM outputs to strict Python data models and domain ontologies. |
| **Multi-Engine Storage** | Qdrant / LanceDB / pgvector / Neo4j / NetworkX | Supports flexible relational, vector, and graph database backends. |

#### **How Graph-Memex Implements & Adapts Cognee**
* **Pydantic/BAML Extraction Layer:** MEMEX adopts Cognee's `Cognify` design pattern: using Pydantic models with local **Ministral 3 8B** (via JSON Schema decoding) to perform typed entity-relation extractions.
* **Hybrid Vector-Graph Retrieval in MongoDB:** Adapts Cognee's search strategies by combining native MongoDB `$vectorSearch` with `$graphLookup` neighborhood expansion and re-ranking inside FastMCP tools.

---

### **4. Evaluation & Key Findings**
* **Benchmark Performance:** Evaluated on multi-hop QA benchmarks (**HotPotQA**, **2WikiMultiHopQA**, **MuSiQue**).
* **Systematic Tuning Gains:** Demonstrates that systematic optimization of chunking boundaries, graph schemas, and retrieval strategies yields consistent performance gains over fixed baseline RAG pipelines.

---

### **5. Master 7-Way Graph RAG Taxonomy Comparison Table**

| Feature | Microsoft GraphRAG | OSU HippoRAG 2 | HKU LightRAG | Zep Graphiti | fastbmRAG | A-MEM | Cognee |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Primary Focus** | Global QFS | **Deep Recall** | **Low-Cost Ingestion** | **Temporal Memory** | **Fast Literature** | **Self-Evolving Memory** | **Modular ECL Pipeline** |
| **Graph Primitive** | Leiden Clusters | Dual-Node Graph | Key-Value Profiles | Bi-Temporal Graph | Draft-and-Refine | Zettelkasten Notes | **Multi-Engine Graph+Vector** |
| **Core Mechanism** | Map-Reduce | Joint Vector PPR | Dual-Level KV | Temporal Filtering | Vector Linking | Agent Link Evolution | **Hybrid Vector+Graph Search** |
| **Structured Output** | Basic JSON | OpenIE Triples | Key-Value Descriptions | Episodic Triples | Abstract Skeleton | Structured Attributes | 🟢 **Pydantic / BAML Models** |
| **MEMEX Role** | Macro Briefings | Review Engine | Multi-Modal Intake | Temporal Sync | Paper Pipeline | Proactive Evolution | **Modular Intake & MCP Search** |

---

### **6. Strategic Implications for Graph-Memex (`me-mex/SPEC.md` & Literature Review)**
* **ECL Pipeline Standard:** Standardizes MEMEX's backend data pipeline into explicit **Extract** (file parsing), **Cognify** (Pydantic LLM extraction & MongoDB document formatting), and **Load** (MongoDB node/edge/vector insertion) phases.

---

## PaperQA2: https://arxiv.org/pdf/2409.13740

### **Paper Metadata**
* **Title:** Language agents achieve superhuman synthesis of scientific knowledge (PaperQA2)
* **Authors:** Michael Skarlinski, Sam Cox, Jon Laurent, Andrew D. White et al. (Future House - Sep 2024)
* **ArXiv ID:** [2409.13740](https://arxiv.org/abs/2409.13740)
* **Code Repository:** [Future-House/paper-qa](https://github.com/Future-House/paper-qa)

---

### **1. Core Paradigm Shift (Standard RAG vs. Scientific Agent)**
* **Why Standard RAG Fails on Scientific Literature:** Standard RAG pipelines pass raw retrieved passages directly into the LLM context window. When applied to dense academic papers, irrelevant tokens degrade attention allocation ("lost in the middle" effect), induce hallucinations, and result in ungrounded, un-cited summaries.
* **PaperQA2 Paradigm Shift:** Replaces passive vector-lookup RAG with an **Autonomous Tool-Augmented Scientific Research Agent**. Instead of feeding raw text into generation prompts, PaperQA2 decouples retrieval into discrete evidence-gathering and filtering agent steps, matching or exceeding human subject matter experts across scientific literature synthesis tasks.

---

### **2. Technical Architecture & Agent Execution Loop**

```
 [User Scientific Query]
           │
           ▼
 [Step 1: Structural PDF Ingestion (Grobid)]
   - Parses paper PDFs into TEI/XML (Title, Sections, Tables, Citations)
           │
           ▼
 [Step 2: Paper Search & Vector Retrieval]
   - Retrieves candidate paper passages matching query intent
           │
           ▼
 [Step 3: Reranking Contextual Summarization (RCS) - Core Innovation]
   - Prompts LLM to evaluate EACH candidate chunk independently
   - Scores chunk relevance & writes an isolated, context-aware summary with metadata
           │
           ▼
 [Step 4: Iterative Search Query Refinement]
   - Agent evaluates evidence yield; loops back to Step 2 if context is incomplete
           │
           ▼
 [Step 5: Citation-Grounded Answer Generation]
   - Synthesizes filtered RCS summaries into a cited, Wikipedia-style answer
```

#### **A. Structural Parsing via Grobid**
* Rather than treating papers as flat text, PaperQA2 parses PDFs using **Grobid** to convert documents into structured TEI/XML trees—preserving section boundaries, figures, tables, and inline reference anchors.

#### **B. Reranking Contextual Summarization (RCS)**
* **The Core Architectural Innovation:** Candidate passages identified by vector search are **NEVER passed raw into the final generation prompt**.
* **RCS Execution:** PaperQA2 calls an LLM to evaluate each candidate passage *in isolation*, scoring its relevance ($0\text{--}10$) and writing a brief, context-aware summary containing exact source paper metadata and citation keys.
* **Result:** Uninformative passages and noisy tokens are stripped away before generation, eliminating attention degradation and hallucinated citations.

#### **C. Contradiction Detection Pipeline**
* PaperQA2 introduces automated **literature contradiction detection**: it pairs candidate papers making opposing empirical claims and uses agent critique loops to isolate contradictory findings across scientific corpora.

---

### **3. Implementation Details & Software Ecosystem**

#### **Official Reference Implementation (`Future-House/paper-qa`)**

| Component / Layer | Library / Engine Used | Implementation Mechanics |
| :--- | :--- | :--- |
| **Python Package** | `paper-qa` (`pip install paper-qa`) | Core framework managing agent tool dispatch, RCS execution, and citation tracking. |
| **PDF Parser Layer** | Grobid / PyPDF | Converts raw PDFs into structured XML section hierarchies. |
| **Vector Index & Storage** | FAISS / LiteLLM / Pydantic | Manages embeddings and structured evidence summaries. |
| **LLM & Provider Binding** | LiteLLM (OpenAI, Anthropic, Local) | Executes RCS summarization calls and answer generation. |

#### **How Graph-Memex Implements & Adapts PaperQA2**
* **RCS Evidence Filtering in FastMCP Tools:** MEMEX adopts PaperQA2's **Reranking Contextual Summarization (RCS)** strategy. When an agent tool queries MEMEX for paper evidence, candidates undergo an RCS filtering pass to produce concise, cited evidence snippets before passing context to the user or planner.
* **Grobid Integration:** Standardizes PDF parsing in MEMEX's intake pipeline via Grobid TEI/XML structures.

---

### **4. Evaluation & Key Findings**
* **Superhuman Performance on LitQA2:** Evaluated on **LitQA2** (a challenging benchmark of multi-paper scientific research questions). PaperQA2 achieved **superhuman accuracy**, outperforming human domain experts who had unrestricted internet and search tool access.
* **Wikipedia-Style Synthesis:** Generated scientific summaries that human expert judges rated as significantly more accurate and reliable than human-written Wikipedia entries.
* **Automated Contradiction Discovery:** Identified an average of **2.34 contradictions per biology paper**, with 70% verified as true contradictions by domain experts.

---

### **5. Strategic Implications for Graph-Memex (`me-mex/SPEC.md` & Literature Review)**
* **Agent Evidence Filtering Standard:** Establishes that MEMEX's agent tools should not return raw markdown notes directly; instead, they should pass retrieved notes through an **RCS contextual summarization filter** to ensure 100% cited, hallucination-free context delivery.

---

## Stanford STORM: https://arxiv.org/pdf/2402.14207

### **Paper Metadata**
* **Title:** Assisting in Writing Wikipedia-like Articles From Scratch with Large Language Models (STORM)
* **Authors:** Yuhang Shao, Yucheng Jiang, Kanqi Yao, Abhinav Jackson, Monica S. Lam, Diyi Yang (Stanford University - Feb 2024)
* **ArXiv ID:** [2402.14207](https://arxiv.org/abs/2402.14207)
* **Code Repository:** [stanford-oval/storm](https://github.com/stanford-oval/storm)

---

### **1. Core Motivation & Pre-Writing Innovation**
* **Why Single-Pass Summarization Fails on Complex Topics:** Asking an LLM to generate long-form articles or topic overviews in a single pass leads to shallow consensus, narrow perspectives, structural disorganization, and narrative repetition.
* **STORM Solution:** STORM (**S**ynthesis of **T**opic **O**utlines through **R**etrieval and **M**ulti-perspective Question Asking) decouples long-form writing into two distinct phases: **Pre-Writing Research & Outline Curation** followed by **Section-by-Section Drafting**. It uses simulated multi-perspective agent interviews to discover non-obvious angles and build a rigorous hierarchical outline before writing a single word.

---

### **2. Technical Architecture & 4-Stage Pipeline**

```
 [User Research Topic]
           │
           ▼
 [Stage 1: Topic Perspective Discovery]
   - Analyzes initial reference documents to discover diverse expert personas
   - E.g., for "Autonomous Driving": Safety Engineer, Policy Regulator, ML Researcher
           │
           ▼
 [Stage 2: Perspective-Guided Multi-Agent Discourse]
   - Simulated Multi-Turn Interviews: Persona Agents ──(Ask Questions)──> Topic Expert Agent
   - Topic Expert Agent fetches grounded facts from Search Engine / Corpus
           │
           ▼
 [Stage 3: Information Tree Curation & Outline Generation]
   - Parses multi-perspective interview transcripts into a unified Information Tree
   - Synthesizes tree into a comprehensive Hierarchical Outline
           │
           ▼
 [Stage 4: Section-by-Section Outline-Driven Writing]
   - Generates cited, long-form sections following the curated outline
```

#### **Stage 1: Topic Perspective Discovery**
* STORM analyzes initial background references to discover diverse expert personas relevant to the subject.
* Assigning distinct persona roles forces the system to explore broad technical, societal, and architectural angles instead of converging on generic summaries.

#### **Stage 2: Perspective-Guided Conversational Interviewing**
* Persona agents conduct simulated multi-turn interviews with a grounded **Topic Expert Agent**.
* The Topic Expert Agent queries search engines or database indices to return factual, cited answers to persona questions.

#### **Stage 3: Information Tree & Hierarchical Outline Curation**
* All interview dialogue transcripts are organized into an **Information Tree**.
* An LLM parses the tree to construct a detailed **Hierarchical Outline** (Sections $\rightarrow$ Subsections $\rightarrow$ Key Findings).

#### **Stage 4: Section-by-Section Drafting**
* Each section is written independently using its corresponding subtree of evidence, preventing context overflow and narrative redundancy.

---

### **3. Implementation Details & Software Ecosystem**

#### **Official Reference Implementation (`stanford-oval/storm`)**

| Component / Layer | Library / Engine Used | Implementation Mechanics |
| :--- | :--- | :--- |
| **Python Package** | `knowledge-storm` (`pip install knowledge-storm`) | Core framework managing persona discovery, dialogue simulation, outline curation, and drafting. |
| **Search Engine Interface** | You.com API / Tavily / Google / Bing | Connects the Topic Expert agent to trusted web search or local vector retrieval indices. |
| **Multi-Agent Engine** | `dspy` / LiteLLM / LangChain | Manages multi-agent prompt pipelines, persona state tracking, and output formatting. |

#### **How Graph-Memex Implements & Adapts STORM**
* **Pre-Writing Outline Curation for Deep Research Files:** MEMEX's Standalone Deep Research documents (`jepa_deep_dive.md`, `rl_landscape.md`) act as topic curricula. MEMEX adapts STORM's **perspective discovery & hierarchical outline curation** to structure these deep research lessons before executing section drafts, preventing narrative redundancy across paper notes.

---

### **4. Evaluation & Key Findings**
* **FreshWiki Benchmark:** Evaluated on **FreshWiki** (a dataset of high-quality recent articles) and rated by experienced Wikipedia editors.
* **Structural Gains:** STORM articles showed a **+25% increase in structural organization** and a **+10% increase in topic coverage breadth** compared to outline-driven RAG baselines.

---

### **5. Strategic Implications for Graph-Memex (`me-mex/SPEC.md` & Literature Review)**
* **Curriculum & Lesson Generation Standard:** Standardizes how MEMEX generates topic-level deep research files: run perspective-guided persona interviews over MongoDB paper nodes to build an exhaustive outline before writing standalone lesson files.

---

## Google AI Co-Scientist: https://arxiv.org/pdf/2502.18864

### **Paper Metadata**
* **Title:** Accelerating scientific discovery with Co-Scientist
* **Authors:** Google DeepMind Team (Built on Gemini 2.0 - Feb 2025)
* **ArXiv ID:** [2502.18864](https://arxiv.org/abs/2502.18864)

---

### **1. Core Paradigm Shift (Passive Compilation vs. Evolutionary Scientific Discovery)**
* **Beyond Passive RAG:** Traditional literature systems focus on passive compilation (retrieving and summarizing past documents). Google AI Co-Scientist shifts AI from a passive reader to an **active scientific partner** capable of generating novel, testable research hypotheses.
* **Test-Time Compute Scaling & Tournament Evolution:** Co-Scientist scales test-time compute across a compound multi-agent architecture. Hypotheses undergo an iterative **tournament evolution process** featuring peer critique, Elo ranking, and recursive refinement to maximize novelty, validity, and experimental feasibility.

---

### **2. Technical Architecture & Multi-Agent Tournament System**

```
                         [User Research Goal & Evidence]
                                        │
                                        ▼
                   [Asynchronous Task Execution Queue]
                                        │
        ┌───────────────────────────────┼───────────────────────────────┐
        ▼                               ▼                               ▼
 [Generation Agent]             [Proximity Agent]               [Reflection Agent]
 (Formulates novel             (Clusters hypotheses in          (Conducts virtual
  hypotheses via search)        embedding space for diversity)   peer reviews)
        │                               │                               │
        └───────────────────────────────┼───────────────────────────────┘
                                        │
                                        ▼
                                [Ranking Agent]
                        (Hosts Pairwise LLM Debates &
                         computes dynamic Elo ratings)
                                        │
                                        ▼
                                [Evolution Agent]
                        (Refines top-ranked hypotheses
                         based on peer critique)
                                        │
                                        ▼
                               [Meta-Review Agent]
                        (Synthesizes tournament state into
                         executive scientific briefs)
```

#### **A. Specialized Agent Roles**
1. **Generation Agent:** Uses web tools and literature databases to formulate novel research hypotheses.
2. **Proximity Agent:** Projects candidate hypotheses into semantic embedding spaces to cluster them, enforcing exploration diversity and preventing redundant idea paths.
3. **Reflection Agent:** Acts as an automated reviewer, performing rigorous virtual peer reviews on candidate hypotheses to evaluate mechanistic feasibility, safety, and novelty.
4. **Ranking Agent:** Runs an **Idea Tournament**, pitting pairs of candidate hypotheses against each other in debate loops to calculate dynamic **Elo ratings**.
5. **Evolution Agent:** Mutates and refines top-ranked hypotheses based on peer critiques from the Reflection Agent.
6. **Meta-Review Agent:** Synthesizes the overall state of the tournament into structured scientific summaries.

#### **B. Test-Time Compute Scaling**
* Co-Scientist demonstrates that scaling test-time compute (running more tournament debate rounds and agent critique iterations) directly improves hypothesis quality, accuracy, and scientific novelty over time.

---

### **3. Empirical Validation & Real-World In Vitro Discovery**
* **Real-World Laboratory Validation:** Co-Scientist was validated across biomedical tasks (drug repurposing, target discovery, anti-microbial resistance).
* **Acute Myeloid Leukemia (AML) Benchmark:** Co-Scientist identified novel drug repurposing candidates and synergistic combination therapies for AML, which were subsequently **validated through real-world *in vitro* laboratory experiments**.

---

### **4. Strategic Implications for Graph-Memex (`me-mex/SPEC.md` & Literature Review)**
* **Proactive Link Discovery & Tournament Ranking in MEMEX:** MEMEX adapts Co-Scientist's tournament evolution loop. When new papers or notes are ingested, background agent workers don't just store static edges—they run reflection and ranking loops to propose novel connections, score relationship confidence via Elo-style tournaments, and update overall research takeaways in `overall_insights.md`.

---

## Nested Learning: https://arxiv.org/pdf/2512.24695

### **Paper Metadata**
* **Title:** Nested Learning: The Illusion of Deep Learning Architectures
* **Authors:** Behnam Neyshabur et al. (Dec 2025)
* **ArXiv ID:** [2512.24695](https://arxiv.org/abs/2512.24695)

---

### **1. Core Paradigm & Philosophy**
* **Beyond Single-Objective Optimization:** Current deep learning models treat training as a flat, single-level optimization problem. Nested Learning (NL) reformulates machine learning as a set of **nested, multi-level, and/or parallel optimization problems**, each possessing its own **context flow** operating across distinct timescales.
* **Key Theoretical Insights:**
  1. **Optimizers as Memory Modules:** Standard gradient-based optimizers (Adam, Momentum SGD) are shown to be associative memory modules that compress gradient context flows.
  2. **Self-Modifying Learning Modules:** Sequence models can learn how to modify their own update algorithms over time.
  3. **Continuum Memory System:** Replaces the rigid binary division of Short-Term vs. Long-Term memory with a continuous multi-level memory system operating across nested update frequencies.

---

### **2. Technical Architecture & The "Hope" Continual Learning Module**

```
 [Nested Multi-Level Context Flows]

 Level 0 (Fast Inner Loop):    Working Context / Activation Updates (Real-Time)
        │
        ▼
 Level 1 (Medium Inner Loop):  In-Context Memory & Associative State Compression
        │
        ▼
 Level 2 (Slow Outer Loop):    Parametric Weight / Update Algorithm Modification
```

* **Self-Modifying Sequence Model:** Learns meta-rules to dynamically adjust its internal state updates based on context.
* **Continuum Memory Structure:** Allows information to transition smoothly across multiple retention rates without catastrophic forgetting.
* **Hope Module:** Combines self-modifying updates with continuum memory, demonstrating SOTA results on continual learning, knowledge incorporation, and long-context reasoning.

---

### **3. Strategic Implications & Pattern Transfer to Graph-Memex (`me-mex/SPEC.md`)**

While Nested Learning operates natively at the model/architecture level, its core principles provide invaluable structural patterns for **Agentic Graph-Memex**:

#### **A. Multi-Timescale Context Flow Architecture**
Graph-Memex instantiates Nested Learning's continuum memory at the agent system level across four nested timescales:

| Timescale / Layer | NL Equivalent | Graph-Memex Implementation |
| :--- | :--- | :--- |
| **Fastest (Real-Time)** | Level 0 (Activation Context) | FastMCP Agent working memory & query context window. |
| **Fast (Streaming)** | Level 1 (Fast Associative) | LightRAG / fastbmRAG incremental ingestion into MongoDB (`deeper_read_notes.md`). |
| **Medium (Evolutionary)** | Level 2 (Associative Memory) | HippoRAG 2 / A-MEM dynamic PageRank & retroactive note updates (`overall_insights.md`). |
| **Slowest (Continuum)** | Level 3 (Outer Optimization) | FSRS-DAG Memory decay scheduling & GraphRAG macro-community briefings. |

#### **B. Self-Modifying System Rules (No Model Fine-Tuning Required)**
* Rather than performing expensive parametric model fine-tuning, Graph-Memex applies NL's **self-modifying principles at the agentic metadata level**.
* Background agent loops evaluate past link suggestions and extraction errors, dynamically modifying system prompts, entity disambiguation thresholds, and relationship weighting rules without touching underlying LLM weights.

---

## ARTS: https://arxiv.org/abs/2606.21891

### **Paper Metadata**
* **Title:** Learning the ARTS of Search for Automated Discovery
* **Authors:** AI Research Team (June 2026)
* **ArXiv ID:** [2606.21891](https://arxiv.org/abs/2606.21891)

---

### **1. Core Motivation & Problem Addressed**
* **Flaws in Heuristic Tree Search (MCTS) for Automated Discovery:** Traditional tree search algorithms (e.g. MCTS) used in automated scientific discovery suffer from two fundamental flaws:
  1. **Conflating Hypothesis Merit with Execution Quality:** Heuristic algorithms penalize a promising hypothesis whose initial code/experiment execution had minor implementation bugs, while over-rewarding a mediocre hypothesis simply because its execution script was heavily polished.
  2. **Context Window Pruning Loss:** As search trees grow, execution logs exceed context window limits, forcing algorithms to prune historical search branches—often accidentally discarding non-obvious, high-value candidate solutions.
* **ARTS Solution:** Introduces **Agentic Reasoning for Tree Search (ARTS)**, deploying a reasoning language model that inspects prior logs to diagnose *why* a failure occurred (implementation bug vs. flawed hypothesis) paired with **Test-Time Training (TTT)** to distill search tree memory directly into model weights without context pruning.

---

### **2. Technical Architecture & Key Innovations**

```
 [Hypothesis & Experiment Search Space]
                   │
                   ▼
 [Reasoning LLM Search Navigator (ARTS)]
   ├── Log Inspection: Diagnoses (Code Bug vs. Flawed Hypothesis)
   └── Branch Selection: Selects promising underlying hypothesis
                   │
                   ▼
 [Test-Time Training (TTT) Memory Retention]
   - Distills search tree history directly into local model weights
   - Eliminates context truncation & historical path pruning
                   │
                   ▼
 [Experimental Execution & Discovery Verification]
```

#### **Innovation A: Diagnostic Reasoning (Bug vs. Hypothesis Merit)**
* Instead of scoring hypothesis branches based purely on raw execution metrics, ARTS uses a reasoning LLM to inspect execution logs and stack traces.
* It explicitly diagnoses whether an experimental failure resulted from an **implementation defect** (e.g., syntax error, hyperparameter bug) or a **fundamentally flawed hypothesis**, ensuring high-potential hypotheses are refined rather than prematurely discarded.

#### **Innovation B: Test-Time Training (TTT) for Zero-Loss Tree Memory**
* Rather than truncating long execution logs to fit context windows, ARTS applies **test-time training (TTT)** during the search process.
* TTT updates model weights on-the-fly to internalize the search tree topology and historical outcomes, allowing lightweight open models (e.g., Qwen3-4B) to retain complete search history while reducing inference costs by **up to 5$\times$** compared to closed-source frontier models.

---

### **3. Evaluation & Key Findings**
* **MLGym & MLEBench Results:** Evaluated across 22 complex machine learning tasks, achieving a **+15.3% relative improvement** over leading tree search baselines (MCTS, Aider, Sakana AI Scientist).
* **Efficiency & Rediscovery:** A TTT-enhanced Qwen3-4B agent matched or surpassed frontier models (Gemini-3 Pro, GPT-o3 reasoning). On partially observable RL benchmarks, ARTS successfully rediscovered human-best recurrent memory architectures that standard MCTS pruned away.

---

### **4. Strategic Implications for Graph-Memex (`me-mex/SPEC.md` & Literature Review)**
* **Diagnostic Logging in Experimental Nodes (`EXPERIMENT`):** When Graph-Memex tracks experimental runs, background agents should apply ARTS-style diagnostic reasoning—separating transient execution bugs from baseline algorithmic flaws before updating node confidence scores.
* **Zero-Loss Graph Memory in MongoDB:** Validates MEMEX's design choice of storing complete execution graphs in MongoDB, avoiding context truncation by fetching topological subgraphs via `$graphLookup` + FSRS scheduling.

---

## ScientistOne: https://arxiv.org/pdf/2605.26340

### **Paper Metadata**
* **Title:** ScientistOne: Towards Human-Level Autonomous Research via Chain-of-Evidence
* **Authors:** AI Research Team (May 2026)
* **ArXiv ID:** [2605.26340](https://arxiv.org/abs/2605.26340)

---

### **1. Core Motivation & The Verifiability Crisis**
* **The Integrity Crisis in Autonomous Research Agents:** Contemporary AI research agents (Sakana AI Scientist, Aider, etc.) produce impressive-looking paper manuscripts and code, but contain hidden structural integrity failures:
  * **Hallucinated References:** Up to 21% of citations in baseline generated papers are hallucinated or fabricated.
  * **Unverified Metric Scores:** Score verification (re-running code to verify reported table scores) passes in as few as 42% of generated manuscripts.
  * **Method-Code Disconnect:** Text descriptions of methods diverge from the actual Python implementation code 20% to 80% of the time.
* **ScientistOne Solution:** Introduces **Chain-of-Evidence (CoE)**, an architectural framework requiring every statement, metric, and citation to be hard-linked by construction to its underlying evidence source (code execution logs, raw metric JSONs, verified paper databases).

---

### **2. Technical Architecture & CoE Integrity Audit**

```
 [Research Task & Literature Input]
                 │
                 ▼
 [Chain-of-Evidence (CoE) Engine]
   ├── Reference Verification: Cross-checks citations against OpenAlex / DOI API
   ├── Method-Code Alignment: Verifies text descriptions match Python ASTs
   └── Score Verification: Hard-links reported numbers to raw metric JSON logs
                 │
                 ▼
 [CoE Audit Pipeline (4 Verification Passes)]
   1. Score Verification Check (Re-runs code to confirm metrics)
   2. Specification Violation Check (Confirms benchmark rules compliance)
   3. Reference Verification Check (Zero hallucinated references)
   4. Method-Code Alignment Check (AST-to-Text verification)
                 │
                 ▼
 [Verifiable Human-Level Manuscript & Codebase]
```

#### **A. Chain-of-Evidence (CoE) by Construction**
* Every generated claim, citation, and metric is assigned an explicit **provenance anchor**:
  * *Citations* are validated against external scholarly APIs (OpenAlex, Semantic Scholar, CrossRef) before insertion.
  * *Performance Metrics* in text and tables must reference an exact, reproducible key in execution logs (`metrics.json`).
  * *Method Descriptions* undergo AST static analysis to ensure natural language text accurately reflects code implementation.

#### **B. The 4 CoE Audit Integrity Checks**
1. **Score Verification:** Independent execution checks confirming reported scores match execution output.
2. **Specification Violation Check:** Audits code to verify benchmark rule compliance.
3. **Reference Verification Check:** Ensures zero hallucinated DOIs/authors.
4. **Method-Code Alignment Check:** Verifies AST alignment between text and code.

---

### **3. Evaluation & Key Findings**
* **Flawless Integrity Metrics:** Across 75 generated papers spanning 5 frontier research tasks, ScientistOne achieved:
  * **0% Hallucinated References** (0/337 vs. up to 21% baseline hallucination rate).
  * **100% Score Verification** (12/12 verified).
  * **Highest Method-Code Alignment** (14/15 verified).
* **MLE-Bench & Parameter Golf Benchmark:** Achieved Gold Medals on MLE-Bench tasks and state-of-the-art results on Parameter Golf, matching or exceeding human expert performance while baselines failed audit checks entirely.

---

### **4. Strategic Implications for Graph-Memex (`me-mex/SPEC.md` & Literature Review)**
* **Chain-of-Evidence Schema in MongoDB:** Every `PAPER`, `INSIGHT`, and `EXPERIMENT` node in Graph-Memex includes explicit `provenance_links` mapping claims back to exact raw source text offsets, file paths, or execution log hashes.
* **CoE Citation Audit in FastMCP Ingestion:** FastMCP ingestion tools enforce DOI/OpenAlex verification and AST method-code checks before committing new paper notes or experimental logs into MongoDB collections.

---

## EvoFSM: https://arxiv.org/abs/2601.09465

### **Paper Metadata**
* **Title:** EvoFSM: Controllable Self-Evolution for Deep Research with Finite State Machines
* **Authors:** AI Research Team (Jan 2026)
* **ArXiv ID:** [2601.09465](https://arxiv.org/abs/2601.09465)

---

### **1. Core Motivation & Controllable Self-Evolution**
* **The Dilemma of Research Workflows:** Fixed agent workflows (rigid step-by-step pipelines) fail on complex, open-ended research queries. On the other hand, unconstrained self-evolving agents (which freely rewrite their own Python code or system prompts) suffer from instruction drift, infinite loops, hallucinations, and system instability.
* **EvoFSM Solution:** Introduces **EvoFSM**, a structured self-evolving framework that achieves both adaptability and safety by formalizing research workflows as an explicit **Finite State Machine (FSM)**. Evolution occurs through constrained FSM graph transformations rather than unconstrained code rewriting.

---

### **2. Technical Architecture & Decoupled Optimization**

```
 [Deep Research Query]
           │
           ▼
 [Finite State Machine (FSM) Execution Engine]
           │
           ├─────────────────────────────────────────┐
           ▼                                         ▼
 [Macroscopic Flow Optimization]           [Microscopic Skill Optimization]
 (State-Transition Graph Logic)            (State-Specific Prompts & Tools)
           │                                         │
           └────────────────────┬────────────────────┘
                                │
                                ▼
         [Critic-Guided Constrained FSM Operations]
         (Add State, Modify Transition, Refine Prompt)
                                │
                                ▼
         [Self-Evolving Trajectory Memory Engine]
   - Successful Trajectories ──> Distilled into Reusable Priors
   - Failure Trajectories   ──> Distilled into Hard Constraints
```

#### **A. Decoupled Optimization Space**
1. **Macroscopic Flow (Graph Topology):** State-transition logic defining how the agent moves between research phases (e.g., *Query Expansion $\rightarrow$ Subgraph Search $\rightarrow$ Evidence Synthesis $\rightarrow$ Verification*).
2. **Microscopic Skill (State-Level Behavior):** State-specific prompt instructions, tool invocation parameters, and extraction rules inside an individual state.

#### **B. Critic-Guided Constrained Operations**
* FSM modifications are restricted to a small set of safe, verified structural operations (e.g., inserting a verification state, altering a transition condition, or tuning a state prompt) guided by an automated Critic module.

#### **C. Self-Evolving Trajectory Memory**
* **Successful Trajectories:** Distilled into **reusable workflow priors** stored in memory to accelerate future similar queries.
* **Failed Trajectories:** Distilled into **hard behavioral constraints** to prevent the agent from repeating flawed search patterns.

---

### **3. Evaluation & Key Findings**
* **DeepSearch Benchmark SOTA:** Reached **58.0% accuracy** on the DeepSearch multi-hop research benchmark, outperforming unconstrained self-rewriting agent baselines and fixed-workflow RAG systems.
* **Generalization:** Demonstrated superior stability and task completion across interactive decision-making and open-ended literature synthesis tasks.

---

### **4. Strategic Implications for Graph-Memex (`me-mex/SPEC.md` & Literature Review)**
* **FSM Workflow Architecture for FastMCP Tools:** Models Graph-Memex agent workflows (data intake, connection discovery, morning review queue generation) as explicit **Finite State Machines (FSMs)** with clear state transitions, preventing unconstrained agent loops or prompt drift.
* **Trajectory Priors in MongoDB:** Successful graph traversal paths and research synthesis trajectories are saved in MongoDB as **reusable workflow priors**, optimizing future deep research queries over the knowledge graph.

---

## Summary

1. GraphRAG has triplet graphs for each chunk followed by community detection at multiple levels with corresponding community report, searched using map-reduce for global and entity-anchored (seeds) for local, but need to re-index everytime.
2. HippoRAG uses LLM as the neocortex, a knowledge graph made with passages and phrases (nouns and entities) as the hippocampus and a mapper from query to seeds as the parahippocampal cortex. These seeds are then used to perform pagerank on the graph from phrase to phrase and phrase to passage.
3. HippoRAG does the exact same thing as GraphRAG to extract entities and phrases using OpenIE to get structured outputs, we could be using LangChain or LlamaIndex for extracting chains as well.
4. HippoRAG 2 tries to fix bias towards high entity count in HippoRAG leading to poor single-hop performance using RAG as non-parametric continual memory with factual memory for single-hop, associative memory for multi-hop and sensemaking for global. It includes passage-passage for context similarity on top of phrase-phrase and passage-phrase in HippoRAG.
5. HippoRAG 2 uses the passage-passage edges so that single-hop usages can directly go through dense passages while multi-hop can make use of phrase-passage associations.
6. LightRAG makes storage faster by KV profiling followed by efficient retrieval using the high-level and low-level separation followed by merging, doesn't require global re-clustering. Good for ingestion, not for retrieval.
7. LightRAG generalizes upon the above assuming that every query has some stuff that's single-hop and other stuff that's multi-hop so needs to be separated.
8. Graphiti uses a bi-temporal schema (valid time and transaction time) where obsolete facts are invalidated rather than deleted to avoid being stuck in a loop. Not good at retrieval, uses BM25 and vector search.
9. Graphiti retains old connections, so like if you said that you stopped using nike and use adidas then it would retain information about nike but in past sense to allow old and new compartmentalized search without messing up.
10. fastbmRAG first processes abstract to get baseline graph and then improves with the full details, good idea for processing long contexts correctly and without duplicates.
11. fastbmRAG is LightRAG for very well-structured papers with abstract and the rest and that's actually faster for this specific set of data.
12. A-MEM also focuses on static memory bottleneck by organizing memory into an interconnected graph of self-contained zettelkasten notes by first getting json, then dynamic link and retroactive memory evolution for future dynamic link computation. Still uses vector similarity and tag overlap.
13. A-MEM is more of an alternative to the OpenIE method used in previous papers to extract the graph. The text is converted into a digital index card with metadata, etc. called a note and links between notes are constructed by an LLM judge. It has the memory evolution technique that helps ensure notes get improved as we add more and more.
14. Cognee uses extract for chunking and metadata tagging, then cognify using pydantic, entity disambiguation and vector embedding and load across relational, vector and graph stores.
15. Cognee is an orthogonal approach using a structured data control plane and infra wrapper to unify graph (entities), vector (entities and text) and relational (text) databases. Memify does the reweighting of the memory to improve based on feedback.
16. PaperQA2 parses pdfs into XML using grobid, then get passages matching query, score them using LLMs with reranking contextual summarization, loop back for more evidence and answer once ready.
17. STORM is for automated writing performing pre-writing research based on expert personas followed by multi-turn interviews between agents with those personas to compute an information tree followed by content generation.
18. Co-Scientist uses a generation agent to formulate hypothesis, proximity agent clusters it in the embedding state, reflection agent performs peer reviews, ranking agent hosts LLM debates about it and the evolution agent ranks them to perform meta-review using the meta-review agent to compute briefs.
19. Nested learning is more focused on optimizers as associative memory, sequence models to improve update algorithms and multi-level memory.
20. ARTS improves upon MCTS for automated discovery to inspect prior logs for failure diagnosis and test-time training to distill memory into model weights, to avoid missing out on those failures as the logs expand beyond context limit.
21. ScientistOne improves upon the sakana scientist containing integrity failures by relying on chain of evidence be it code logs, metric JSONs or verified papers, can be used with the graph links we constructed to require every statement, metric and citation to be hard-linked to underlying source.
22. EvoFSM is a self-evolving research framework using a finite state machine with state-transition graph logic for macroscopic flow and state-specific promts and tools for microscopic skill optimization.

# Master Research Synthesis & Literature Survey: Me-Mex

> **Document Purpose**: This document serves as the master research reference for **Me-Mex**, consolidating theoretical literature surveys, multi-agent debate frameworks, automated scientific discovery architectures, and deep-dive paper notes into a single comprehensive synthesis.

---

# Part 1: Knowledge Graph RAG & Agentic Memory Literature Survey

Retrieval-Augmented Generation (RAG) has evolved from flat semantic vector lookups into structured, topology-aware knowledge representations and dynamic agentic memory substrates. Standard vector RAG segments text into arbitrary chunks and retrieves top-$k$ passages via approximate nearest-neighbor search. While efficient, vector search fails on multi-hop associative reasoning and global sensemaking across corpora.

## Comparative Framework Analysis

| Framework | Core Knowledge Primitive | Traversal & Retrieval Mechanism | Ingestion & Update Overhead | Primary Failure Modes & Trade-offs | Key References |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Microsoft GraphRAG** | Entity-relation triples grouped into hierarchical Leiden communities | Multi-level community report summarization; Map-Reduce Global Search vs. Local Search | High; requires exhaustive LLM-based triple extraction & Leiden clustering | High indexing cost; batch-oriented; dynamic updates require partial re-clustering | Edge et al. (2024) |
| **HippoRAG & HippoRAG 2** | Dual-node (passage and phrase) graph backed by hippocampal indexing | Personalized PageRank over phrase-passage adjacency; online LLM recognition filtering | Moderate; offline OpenIE; online graph traversal executes without multi-turn LLM hops | Uneven entity density skews probability mass toward evidence-poor nodes | Bernal et al. (2024) |
| **LightRAG** | Low-level entity nodes combined with high-level conceptual relation themes | Dual-level retrieval (local entity matching + global relation key search) | Low; fast incremental updates via key-value profiling and graph deduplication | Lower structural expressiveness than complete community clustering graphs | Guo et al. (2024) |
| **Fast GraphRAG** | Domain-constrained entity-relation graph | Seed entity vector search followed by Personalized PageRank traversal | Low-to-moderate; native incremental insertions with local checkpointing | Requires upfront domain prompt and entity constraints to preserve precision | (2024) |
| **Zep / Graphiti** | Bi-temporal context graph (entities, relationships, episodes) | Hybrid retrieval: dense vector search, BM25 keyword matching, temporal edge filtering | Low-latency streaming; temporal fact invalidation rather than destructive deletion | High operational complexity for bi-temporal indexing; requires graph database backends | Zep (2024) |
| **A-MEM** | Atomic Zettelkasten memory notes with structured semantic attributes | Multi-attribute vector similarity search paired with dynamic link generation | Adaptive; background LLM passes trigger retroactive updates across historical notes | Cascading updates risk semantic drift if update heuristics are unconstrained | (2024) |
| **Cognee** | Extract-Cognify-Load pipeline over graph, vector, and relational stores | Multi-hop graph search with vector re-ranking (supporting 14+ hybrid strategies) | Moderate; asynchronous classification, chunking, extraction, and loading pipeline | Multi-engine operational footprint (relational, vector, and graph layers) | Cognee (2024) |

---

# Part 2: Multi-Agent Systems, Consensus Topologies & Automated Co-Scientists

Multi-agent architectures decompose complex operational objectives into bounded sub-tasks governed by specialized execution units. This structural division directly mitigates monolithic failure modes, including token saturation, compounding reasoning errors, and cascading hallucinations.

## Coordination Topologies & Control Characteristics

```
┌────────────────────────────────────────────────────────────────────────────────────────┐  
│ Coordination Topologies & Control Characteristics                                     │  
├──────────────────────────┬─────────────────────────────┬───────────────────────────────┤  
│ Topology                 │ Control Flow Mechanism      │ Primary Failure Mode          │  
├──────────────────────────┼─────────────────────────────┼───────────────────────────────┤  
│ Hierarchical Supervision │ Centralized delegation      │ Cascading plan failure        │  
│ Finite State Machines    │ Deterministic transitions   │ Rigid path exceptions         │  
│ Decentralized Swarms     │ Dynamic peer handoffs       │ Non-convergent cycling        │  
│ Evolutionary Consensus   │ Tournament debate & Elo     │ High inference compute cost   │  
└──────────────────────────┴─────────────────────────────┴───────────────────────────────┘
```

### Scientific Synthesis & Automated Co-Scientist Frameworks

| System / Framework | Architectural Paradigm | Primary Components | Synthesis & Verification Loop | Key Strengths & Limits |
| :--- | :--- | :--- | :--- | :--- |
| **PaperQA2** | Modular Tool-Augmented Agent | Paper Search, Reranking Contextual Summarization (RCS) | Iterative query refinement; context-aware chunk summarization before generation | Matches/exceeds expert human precision on literature synthesis; compute intensive |
| **Stanford STORM** | Perspective-Guided Discourse | Topic Perspective Discovery, Conversational Interviewing | Pre-writing discourse: simulated specialist personas interview web-grounded topic experts | Excels at breadth and long-form structural coherence; susceptible to shallow consensus |
| **Google AI Co-Scientist** | Evolutionary Multi-Agent Architecture | Asynchronous Task Queue; Generation, Reflection, Ranking Agents | Elo tournament ranking; pairwise debate loops; meta-review evolution | Validated on real biomedical discovery; requires high-capacity LLM infrastructure |
| **Sakana AI Scientist** | Autonomous Discovery Loop | Idea Generation, Code Execution via Aider, Manuscript Generation | Automated peer-review loop based on conference rubrics; iterative tree search | Full lifecycle autonomy; vulnerable to template filling and code execution drift |

---

# Part 3: Deep-Dive Paper Notes & Technical Summaries

## 1. Microsoft GraphRAG (ArXiv: 2404.16130)

### 4-Stage Technical Pipeline
1. **Stage 1 (Text Chunking & Local Extraction)**: Divides text into small chunks (300–600 tokens); extracts entities, relationships, and claims per chunk via OpenIE prompts.
2. **Stage 1.5 (Global Graph Union)**: Merges entity instances across chunks into canonical nodes and aggregates edge weights (occurrence count/confidence).
3. **Stage 2 (Hierarchical Leiden Community Detection)**: Runs the Leiden algorithm on the global graph to form hierarchical partitions (Level 0 Macro domains $\rightarrow$ Level 3 Micro clusters).
4. **Stage 3 (Pregenerated Community Summarization)**: LLM generates structured Community Reports offline during indexing.
5. **Stage 4 (Query Execution)**: Map-Reduce Global Search over community reports for broad QFS; entity-anchored Local Search for fact lookups.

---

## 2. Stanford STORM: Synthesis via Multi-Perspective Discourse

- **Pre-Writing Research Phase**: Discovers diverse expert perspectives and adopted personas conduct multi-turn interviews with web retrieval tools.
- **Hierarchical Outline Curation**: Transforms interview transcripts into an information tree to construct an exhaustive outline prior to section drafting.
- **Key Takeaway for Graph-Memex**: Pre-writing perspective discovery prevents single-pass summary redundancy and structures knowledge into clear conceptual hubs.

---

## 3. Google AI Co-Scientist: Idea Evolution & Pairwise Elo Debates

- **Asynchronous Task Architecture**: Coordinates Generation, Proximity, Reflection, and Ranking agents.
- **Idea Tournaments**: Evaluates candidate hypotheses through pairwise debate matches, updating Elo scores using standard logistic distribution dynamics.
- **Evolutionary Refinement**: Evolution agents mutate top-ranked hypotheses based on peer review feedback.
- **Key Takeaway for Me-Mex**: Specialist Personas execute over mutually exclusive sub-graph partitions without requiring consensus or multi-persona debate. Nodes evolve independently as personas reorganize and split over-clustered concepts using underlying passage context.

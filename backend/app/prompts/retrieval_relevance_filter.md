<!--
  Step 2 retrieval: relevance filter on explored subgraph (before answer synthesis)
-->
You narrow a wide graph traversal down to concepts that **directly** answer the user's question.

The navigator already explored many nodes (broad search). Your job is **not** to keep everything—only keep concepts whose titles/descriptions are **necessary** to answer the exact query.

Rules:
1. **Query-first:** Match the user's specific topic, entities, and comparison (e.g. "decision models" → decision-model papers/hubs; **exclude** unrelated domains like world models, diffusion, RSI unless the query explicitly asks for them).
2. **Minimal sufficient set:** Prefer the smallest set that fully answers the question. Drop sibling branches that were explored but are off-topic.
3. **Mutable hubs:** Keep a hub only if it anchors relevant evidence for this query.
4. **Immutable evidence:** Keep only immutables that support the selected hubs **and** the question (drop paper facts from other domains).
5. **ROOT provenance:** Keep a source document only if at least one of its selected immutables is included.
6. If nothing is relevant, select the single best-matching concept_index and explain in `answer_scope`.

Return JSON:
{{
  "selected_concepts": [
    {{ "concept_index": 1, "rationale": "Why this node is in scope for the query." }}
  ],
  "answer_scope": "One sentence: what you will answer and what you will deliberately omit."
}}

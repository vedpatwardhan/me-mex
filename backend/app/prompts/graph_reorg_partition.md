<!--
  Unified partition: sub-concept formulation + neighbor re-wiring (Phase 4)
-->
You are {{ department_name }}, the Graph Navigator performing graph maintenance.
Your task is a **unified partition** of over-clustered mutable concept '{{ node_id }}': propose sub-concepts **and** assign every listed neighbor to a sub-concept or overflow target in **one** response.

{{ split_strategy_block }}

OPERATIONAL MODE: {{ mode }}

PARTITION GOAL (max coverage):
1. Consider **all** neighbors listed (immutable evidence and mutable concepts together).
2. Propose sub-concepts and assign neighbors so each sub-concept covers **as many neighbors as possible** (aim for coherent groups of ~2–3 when n allows).
3. Assign **every** `neighbor_index` exactly once in `rewired_edges`.
4. Avoid one-neighbor sub-concepts when n ≥ 4 unless no better grouping exists.
5. Do **not** copy neighbor titles verbatim for new sub-concepts when grouping multiple neighbors — synthesize umbrella titles.

OVERFLOW (when a neighbor cannot join any sub-concept group):
- Use `connect_to_sub_alias`: **"{{ overflow_alias }}"**

GENERAL RULES:
1. Distinct sub-concepts: clear title and synthesized description per sub-concept.
2. Cardinality:
   - Neighbors in scope: {{ neighbor_count }}.
   - Propose at least {{ min_allowed_sub_concepts }} and at most {{ max_allowed_sub_concepts }} sub-concepts (bounded by n // 2 when n ≥ 2).
3. Parent update (compulsory):
   - Provide `parent_title` and `parent_description` for the split target.
   - If title is 'Everything', keep `parent_title` as 'Everything'.
4. Every sub-concept alias that appears in `rewired_edges` must exist in `sub_concepts`. Prefer giving each sub-concept at least one neighbor.

Return JSON format strictly:
{
  "parent_title": "Umbrella Title",
  "parent_description": "Comprehensive description.",
  "sub_concepts": [
    {
      "sub_id_alias": "sub_1",
      "title": "Focused Sub-Concept Title 1",
      "description": "Synthesized description."
    }
  ],
  "rewired_edges": [
    {
      "neighbor_index": 1,
      "connect_to_sub_alias": "sub_1",
      "relation_type": "RELEVANT_TO",
      "description": "Re-wired connection."
    }
  ]
}

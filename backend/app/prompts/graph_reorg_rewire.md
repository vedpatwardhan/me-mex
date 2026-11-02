<!--
  Neighbor edge re-wiring (Step 3 of reorganization)
-->
You are {{ department_name }}, the Graph Navigator performing graph maintenance.
Step 3 (Neighbor Edge Re-Wiring): Assign each direct neighbor of mutable concept '{{ node_id }}' to the most appropriate new sub-concept alias.

OPERATIONAL MODE:
{% if mode == "leaf_outward" %}
MODE: LEAF OUTWARD REWIRING (Phase 2a)
- Rewire immutable evidence leaves to new sub-concepts (or an existing mutable node if it is the perfect semantic home).
- Replace direct leaf-to-target edges with connections through sub-concepts.
{% elif mode == "pure_immutable" %}
MODE: DIRECT OUTWARD LEAF REWIRING
- Rewire each immutable leaf to its designated sub-concept alias.
{% else %}
MODE: MUTABLE CONCEPT REWIRING
- Rewire mutable neighbors to matching new intermediate sub-concepts.
{% endif %}

RULES:
1. Cover every target neighbor in the input list.
2. Each neighbor connects to at least one `sub_id_alias` (multiple only if genuinely cross-cutting).
3. Every sub-concept alias receives at least one neighbor — no idle sub-concepts.

Return JSON format strictly:
{
  "rewired_edges": [
    {
      "neighbor_index": 1,
      "connect_to_sub_alias": "sub_1",
      "relation_type": "RELEVANT_TO",
      "description": "Re-wired connection from neighbor to sub-concept."
    }
  ]
}

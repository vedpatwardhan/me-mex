<!--
  Specialist Persona Neighbor Edge Re-Wiring Prompt Template (Step 3 of 3)
  Iterates over direct neighbor nodes to assign them to newly created intermediate sub-concepts.
-->
You are {{ department_name }}, a Specialist Persona Agent in the knowledge graph.
Your task is Step 3 (Neighbor Edge Re-Wiring): Iterating over direct neighbor nodes connected to concept hub '{{ node_id }}' and assigning each neighbor node to the single most appropriate newly created sub-concept alias.

OPERATIONAL MODE:
{% if mode == "leaf_outward" %}
MODE: LEAF OUTWARD REWIRING (Phase 2a)
- You are rewiring ground-truth immutable evidence leaves outward to the newly formed sub-concepts (or optionally to an existing mutable concept if it is a perfect semantic home).
- Direct connections between the leaves and the hub '{{ node_id }}' will be replaced by connections through the sub-concepts.
{% elif mode == "pure_immutable" %}
MODE: DIRECT OUTWARD LEAF REWIRING
- Rewire each immutable leaf to its designated sub-concept alias.
{% else %}
MODE: MUTABLE CONCEPT REWIRING
- Rewire connected mutable concepts underneath their matching new intermediate sub-concepts.
{% endif %}

RULES:
1. Complete Target Neighbor Coverage: You MUST evaluate and rewire every target neighbor node provided in the input list.
2. Distinct Assignment: Assign each target neighbor node to AT LEAST ONE `sub_id_alias` (or multiple aliases if genuinely relevant to more than one sub-concept).
3. Complete Sub-Concept Coverage: Ensure EVERY newly formulated sub-concept alias receives AT LEAST ONE connecting neighbor. No sub-concept may be left idle without neighbor connections.

Return JSON format strictly:
{
  "rewired_edges": [
    {
      "neighbor_id": "exact_neighbor_node_id_1",
      "connect_to_sub_alias": "sub_1",
      "relation_type": "RELEVANT_TO",
      "description": "Re-wired connection from neighbor to specific sub-concept."
    },
    {
      "neighbor_id": "exact_neighbor_node_id_2",
      "connect_to_sub_alias": "sub_2",
      "relation_type": "RELEVANT_TO",
      "description": "Re-wired connection ensuring sub_2 is also covered."
    }
  ]
}

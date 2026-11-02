<!--
  Neighbor edge re-wiring (Step 3 of reorganization)
-->
You are {{ department_name }}, the Graph Navigator performing graph maintenance.
Step 3 (Neighbor Edge Re-Wiring): Assign **every** direct neighbor of '{{ node_id }}' to a sub-concept or to the overflow target.

{% if is_genesis == "true" %}
GENESIS: Neighbors that cannot join any sub-concept use `connect_to_sub_alias`: **"EVERYTHING"** (remain directly connected to Genesis).
{% else %}
NON-GENESIS: Neighbors that cannot join any sub-concept use `connect_to_sub_alias`: **"ANCESTOR"** (connect to the parent of the split hub in the tree).
{% endif %}

RULES:
1. Cover **every** neighbor in the input list exactly once.
2. Prefer assigning neighbors to the sub-concept alias that best fits semantically (immutable and mutable neighbors may share a sub-concept).
3. Use ANCESTOR or EVERYTHING only when a neighbor cannot reasonably join any proposed sub-concept group.
4. Every sub-concept alias should receive at least one neighbor when possible — avoid idle sub-concepts.

Return JSON format strictly:
{
  "rewired_edges": [
    {
      "neighbor_index": 1,
      "connect_to_sub_alias": "sub_1",
      "relation_type": "RELEVANT_TO",
      "description": "Re-wired connection."
    }
  ]
}

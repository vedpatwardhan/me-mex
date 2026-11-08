<!--
  Unified partition: sub-concepts + overflow neighbors + sub-only rewiring (Phase 4)
-->
You are {{ department_name }}, the Graph Navigator performing graph maintenance.
Your task is a **unified partition** of over-clustered mutable concept '{{ node_id }}': propose sub-concepts, declare overflow neighbors, and assign sub-group neighbors in **one** response.

{{ split_strategy_block }}

OPERATIONAL MODE: {{ mode }}

## AT LEAST ONE SUB-CONCEPT (structure)

Reorganization exists to **subdivide** the hub. You must propose **at least {{ min_sub_concepts }}** entry in `sub_concepts` with valid groupings below.

## MIN-2 PER SUB (absolute — no exceptions)

Every entry in `sub_concepts` must receive **≥ {{ min_sub_neighbors }}** distinct neighbors via `rewired_edges`. **Never** output a sub with 0 or 1 neighbor.

If a thematic hint has only one neighbor, list that neighbor in **`overflow_neighbors`**, not as a thin sub-concept.

## OVERFLOW NEIGHBORS (first-class)

Neighbors that **cannot** join any **≥{{ min_sub_neighbors }}-neighbor** sub group belong in **`overflow_neighbors`** (with a brief `rationale`).

Overflow neighbors are promoted to **{{ overflow_target_label }}** at commit time (not listed in `rewired_edges`).

## DEGREE GOAL (single step)

Prefer **one** partition that moves this hub **toward** degree **below τ** by minting **coherent multi-neighbor subs** (each **≥{{ min_sub_neighbors }}**). Group related neighbors aggressively when thematically defensible. Use **overflow** for stragglers so the parent/orphan load trends down in one commit.

## THREE LIST OUTPUT

| List | Purpose |
|------|---------|
| `sub_concepts` | Sub-hubs to mint / replacement siblings (`sub_1`, `sub_2`, …). Count: **{{ min_sub_concepts }}** to **{{ max_allowed_sub_concepts }}** (≤ n // 2). |
| `overflow_neighbors` | `{ neighbor_index, rationale }` for orphans → {{ overflow_target_label }}. |
| `rewired_edges` | **Sub assignments only** — `{ neighbor_index, connect_to_sub_alias: "sub_*", description }`. **No** EVERYTHING/ANCESTOR here. |

**Coverage:** Every neighbor index **1..{{ neighbor_count }}** appears **exactly once** — either in `rewired_edges` or in `overflow_neighbors`.

PARTITION GOAL (max coverage among subs):
1. Consider **all** neighbors listed (immutable and mutable together).
2. Group into coherent sub-concepts of ~2–3 neighbors when n allows.
3. Do **not** copy neighbor titles verbatim for new sub-concepts — synthesize umbrella titles.

Parent update (compulsory):
- Provide `parent_title` and `parent_description` for the split target.
- If title is 'Everything', keep `parent_title` as 'Everything'.

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
  "overflow_neighbors": [
    {
      "neighbor_index": 5,
      "rationale": "Does not fit any ≥2-neighbor sub group."
    }
  ],
  "rewired_edges": [
    {
      "neighbor_index": 1,
      "connect_to_sub_alias": "sub_1",
      "description": "Optional natural-language note for the new link."
    }
  ]
}

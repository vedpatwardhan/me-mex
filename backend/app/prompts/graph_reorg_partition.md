<!--
  Unified partition: sub-concepts + overflow neighbors + sub-only rewiring (Phase 4)
-->
You are {{ department_name }}, the Graph Navigator performing graph maintenance.
Your task is a **unified partition** of over-clustered mutable concept '{{ node_id }}': propose sub-concepts, declare overflow neighbors, and assign sub-group neighbors in **one** response.

{{ split_strategy_block }}

OPERATIONAL MODE: {{ mode }}

## AT LEAST ONE NEW OR REUSED HUB

Subdivide by **minting new sub-concepts** (`sub_*` in `sub_concepts`) and/or **reusing existing mutable neighbors** as grouping hubs (see below). When you use `connect_to_sub_alias`, list matching entries in `sub_concepts`.

## REUSE EXISTING MUTABLE NEIGHBORS (critical)

If a **mutable** neighbor in the batch already acts as a department hub under the split target, attach additional neighbors to it instead of minting a duplicate:

- Use **`connect_to_existing_neighbor_index`** (batch index of that mutable neighbor).
- **Do not** list that neighbor again in `sub_concepts`.
- **Do not** assign that hub's own index to a new `sub_*` alias (it stays on the split target).
- Immutable-only stragglers may attach to an existing mutable hub with this field.

## REWIRED_EDGES INVARIANTS (absolute)

- **`connect_to_existing_neighbor_index` must differ from `neighbor_index`** — no self-wires.
- **Replacement `sub_1` (parent id reuse)** uses **`connect_to_sub_alias`: `"sub_1"`** only — **not** `connect_to_existing_neighbor_index`.
- `connect_to_existing_neighbor_index` is **only** when neighbor **j** attaches under **another** mutable batch index **k** where **k ≠ j**.

**Bad (replacement split):** `{ "neighbor_index": 1, "connect_to_existing_neighbor_index": 1 }`  
**Good:** `{ "neighbor_index": 1, "connect_to_sub_alias": "sub_1" }` or omit index 1 if it is only the `sub_1` anchor.

## MIN-2 PER NEW SUB (absolute)

Every **new** entry in `sub_concepts` must receive **≥ {{ min_sub_neighbors }}** distinct neighbors via `rewired_edges` using `connect_to_sub_alias`. **Never** output a thin new sub with 0 or 1 neighbor.

If a would-be new sub has only one neighbor, use **`overflow_neighbors`** or **`connect_to_existing_neighbor_index`** to an existing mutable hub instead.

## OVERFLOW NEIGHBORS (first-class)

Neighbors that **cannot** join any **≥{{ min_sub_neighbors }}-neighbor** new sub group belong in **`overflow_neighbors`** (with a brief `rationale`).

Overflow neighbors are promoted to **{{ overflow_target_label }}** at commit time (not listed in `rewired_edges`).

## DEGREE GOAL (single step)

Prefer **one** partition that moves this hub **toward** degree **below τ** by minting coherent multi-neighbor subs and/or strengthening existing mutable children. Use **overflow** for stragglers so the parent/orphan load trends down in one commit.

## THREE LIST OUTPUT

| List | Purpose |
|------|---------|
| `sub_concepts` | **New** sub-hubs to mint (`sub_1`, `sub_2`, …). Count: **0** to **{{ max_allowed_sub_concepts }}** (≤ n // 2) when reusing existing hubs; at least **{{ min_sub_concepts }}** when any row uses `connect_to_sub_alias`. |
| `overflow_neighbors` | `{ neighbor_index, rationale }` for orphans → {{ overflow_target_label }}. |
| `rewired_edges` | Per neighbor: **exactly one** of `connect_to_sub_alias` (new `sub_*`) **or** `connect_to_existing_neighbor_index` (mutable batch index). **No** EVERYTHING/ANCESTOR here. |

**Coverage:** Every neighbor index **1..{{ neighbor_count }}** appears **exactly once** in `rewired_edges` or `overflow_neighbors`, **except** mutable hubs used only as `connect_to_existing_neighbor_index` targets (anchors) need not be listed as assignees.

PARTITION GOAL (max coverage among subs):
1. Consider **all** neighbors listed (immutable and mutable together).
2. Group into coherent sub-concepts of ~2–3 neighbors when n allows.
3. Do **not** copy neighbor titles into **new** `sub_concepts` — synthesize umbrella titles. **Reuse** is correct when the hub already exists in the batch.

Parent update (compulsory):
- Provide `parent_title` and `parent_description` for the split target.
- If title is 'Everything', keep `parent_title` as 'Everything'.

## UMBRELLA DESCRIPTIONS (sub-concepts and parent)

Descriptions are used for **upstream linking and traversal**—each must justify why its assigned neighbors belong together.

- **`sub_concepts[].description`:** **2–4 sentences** (~80–180 words) per minted sub-hub. Name the **shared theme**, list **what kinds of neighbors** belong under this sub (by role/topic, not just titles), and how this sub differs from sibling subs.
- **`parent_description`:** **2–4 sentences** synthesizing the **remaining umbrella** role of the split target after this partition (what still lives on the parent vs what moved to subs or overflow). Do not paste the old hub description verbatim.
- Do not use one-line placeholders; vague umbrellas cause duplicate branches elsewhere in the tree.

Return JSON format strictly:
{
  "parent_title": "Umbrella Title",
  "parent_description": "Two to four sentences on the parent hub's remaining umbrella scope after this split.",
  "sub_concepts": [
    {
      "sub_id_alias": "sub_1",
      "title": "Focused Sub-Concept Title 1",
      "description": "Two to four sentences explaining the coherent theme shared by all neighbors assigned to sub_1 and how it differs from other subs."
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
      "neighbor_index": 2,
      "connect_to_existing_neighbor_index": 1,
      "description": "Attach evidence to existing mutable hub at batch index 1."
    },
    {
      "neighbor_index": 3,
      "connect_to_sub_alias": "sub_1",
      "description": "Optional natural-language note for the new link."
    },
    {
      "neighbor_index": 4,
      "connect_to_sub_alias": "sub_1",
      "description": "Optional natural-language note for the new link."
    }
  ]
}

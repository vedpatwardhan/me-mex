You are conducting a Multi-Persona Debate between domain specialists regarding how to integrate conflicting proposed graph edits into the knowledge graph.

Document Context:
Title: {doc_title}

Conflicting Persona Proposals:
{persona_proposals_json}

Persona Objections & Arguments Raised:
{persona_objections_json}

Task:
Debate and negotiate between the conflicting persona perspectives. Determine the optimal graph resolution:
1. Should concepts be merged into one specific existing domain node?
2. Or should concepts be SUB-DIVIDED into two or more distinct sub-concepts (e.g., one for Domain A and one for Domain B), with optional bridge edges created between domain hubs?
3. Or should they be kept as separate stand-alone nodes linked via relationship edges to both hubs?

Return JSON format strictly:
{
  "resolution_type": "SUBDIVIDE" | "MERGE_SINGLE" | "KEEP_SEPARATE",
  "rationale": "Detailed debate consensus rationale...",
  "merged_target_node_id": "concept_123", // required if MERGE_SINGLE
  "sub_concepts": [ // required if SUBDIVIDE
    {
      "sub_title": "Sub-concept Title A",
      "description": "Sub-concept Description A",
      "target_node_id": "concept_123", // target node to merge into, if applicable
      "passage_ids": []
    }
  ],
  "additional_edges": [
    {
      "source_id": "hub_or_node_id_1",
      "target_id": "hub_or_node_id_2",
      "description": "Bridge edge description..."
    }
  ]
}

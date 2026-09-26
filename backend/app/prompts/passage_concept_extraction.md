You are a knowledge graph concept extractor analyzing a passage chunk from document '{doc_title}'.
Extract 1-3 atomic concepts and their qualitative relationships.

Return JSON format:
{
  "concepts": [
    {"title": "Concise Concept Title", "description": "Atomic markdown summary of the concept"}
  ],
  "relations": [
    {
      "source_title": "Concept A",
      "target_title": "Concept B",
      "relation_type": "BUILDS_UPON" | "SUPERSEDES" | "PARALLEL_TO",
      "description": "Qualitative link explanation"
    }
  ]
}

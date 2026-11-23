You are Me-Mex consolidating intra-document concept extractions.
You are given a document titled '{{ doc_title }}' and a collection of raw concepts collected across passages of the document. A consolidation call may receive the original passage extractions or intermediate canonical concepts from earlier bounded consolidation rounds.
The accompanying user query and section summaries provide context for why this content is being ingested. They are not evidence about the paper.
The input JSON contains `user_intent`, optional `section_summaries`, and `raw_concepts`. Each raw concept carries its original source `passage_indices`; intermediate concepts may already represent several original passages.

IMPORTANT INGESTION RULE - COVERAGE (NO DROPPED PASSAGES):
- Every raw concept MUST contribute to exactly one canonical concept.
- Preserve the union of its original `passage_indices` on the canonical concept. Do not replace original passage indices with local concept indices.
- DO NOT omit or discard any source passage index represented in the input list.
- Consolidation means grouping overlapping ideas—it is NOT permission to drop raw concepts from coverage.
- Do not invent concepts not grounded in the input.

DESCRIPTION QUALITY (for graph linking and hierarchy — not token shaving):
- `doc_description`: **2–4 sentences** executive summary of the whole document (~80–180 words).
- Each canonical `description`: **2–4 sentences** (~80–150 words) that **merge technical substance** from all grouped raw concepts—methods, objects, and claims a reader needs to distinguish this hub from siblings later.
- Name **specific mechanisms, datasets, or metrics** when present in the inputs; avoid one-line slogans.
- `title`: short, specific, unique among the set.

Your task:
1. DOCUMENT GLOBAL SUMMARY:
   - Provide `doc_description` and infer `doc_type` ("paper", "blog", "video", "post").

2. CONSOLIDATE CONCEPTS:
   - Group raw concepts that refer to the same underlying idea under one canonical title:
     - If the input contains more than 6 raw concepts, consolidate to **3 to 5** canonical concepts.
     - If 6 or fewer raw concepts, retain **1 to 3** natural distinct concepts—do not pad.
   - Aggregate all originating `passage_indices` (integers) for each canonical concept, including indices already aggregated by earlier rounds.

Return JSON format:
{{
  "doc_description": "Multi-sentence executive summary with enough detail to orient retrieval.",
  "doc_type": "paper",
  "concepts": [
    {{
      "title": "Canonical Concept Title",
      "description": "Two to four sentences capturing merged technical content from all passages in this group.",
      "passage_indices": [0, 3]
    }}
  ]
}}

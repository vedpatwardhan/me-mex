import json

from app.llm import chains
from app.llm.schemas import (
    CanonicalConcept,
    ConsolidateResult,
    PassageConcept,
    PassageExtractResult,
)
from langchain_core.runnables import RunnableLambda


def test_intradoc_bounds_reduction_and_preserves_source_passage_provenance(monkeypatch):
    mapped_indices = []
    reduce_input_sizes = []

    def structured_llm(schema, *, caller, **_kwargs):
        if caller == "IntraDoc.map":

            def map_passage(inputs):
                chunk = json.loads(inputs.to_messages()[-1].content)
                passage_index = chunk["passage_index"]
                mapped_indices.append(passage_index)
                return PassageExtractResult(
                    concepts=[
                        PassageConcept(
                            idx=0,
                            title=f"Concept from passage {passage_index}",
                            description=f"Grounded description from passage {passage_index}.",
                        )
                    ]
                )

            return RunnableLambda(map_passage)

        assert caller == "IntraDoc.reduce"

        def consolidate(inputs):
            payload = json.loads(inputs.to_messages()[-1].content)
            concepts = payload["raw_concepts"]
            reduce_input_sizes.append(len(concepts))
            passage_indices = sorted(
                {int(index) for concept in concepts for index in concept.get("passage_indices", [])}
            )
            return ConsolidateResult(
                doc_description="Grounded whole-document description.",
                concepts=[
                    CanonicalConcept(
                        title="Consolidated concept",
                        description="Consolidated technical detail from the source passages.",
                        passage_indices=passage_indices,
                    )
                ],
            )

        return RunnableLambda(consolidate)

    monkeypatch.setattr(chains, "structured_llm", structured_llm)
    monkeypatch.setattr(chains, "passage_chunk_size_chars", lambda: 64)
    monkeypatch.setattr(chains.settings, "INGEST_EXTRACTION_CONCURRENCY", 2)
    pipeline = chains._live_intradoc()
    document = " ".join(f"passage-{index} " + "detail " * 5 for index in range(18))

    result = pipeline.invoke({"text": document, "doc_title": "Paper", "user_intent": "deep read"})

    assert len(result["passages"]) > 12
    expected_indices = list(range(len(result["passages"])))
    assert sorted(mapped_indices) == expected_indices
    assert result["concepts"][0]["passage_indices"] == expected_indices
    assert all(size <= 12 for size in reduce_input_sizes)
    assert result["doc_description"] == "Grounded whole-document description."
    assert [passage["text"] for passage in result["passages"]]

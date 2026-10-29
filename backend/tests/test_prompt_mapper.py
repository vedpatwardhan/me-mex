import pytest
from app.services.prompt_mapper import PromptIdMapper


def test_prompt_mapper_registration_and_roundtrip():
    mapper = PromptIdMapper(prefix="passage")
    idx1 = mapper.register("pass_chunk_3a9f02b1")
    idx2 = mapper.register("pass_chunk_8c41de02")
    idx3 = mapper.register("pass_chunk_3a9f02b1")  # duplicate

    assert idx1 == 1
    assert idx2 == 2
    assert idx3 == 1  # idempotent
    assert len(mapper) == 2

    # String & int retrieval
    assert mapper.to_id(1) == "pass_chunk_3a9f02b1"
    assert mapper.to_id("1") == "pass_chunk_3a9f02b1"
    assert mapper.to_id("02") == "pass_chunk_8c41de02"
    assert mapper.to_id(99) is None
    assert mapper.to_id("invalid") is None

    assert mapper.to_index("pass_chunk_3a9f02b1") == 1
    assert mapper.to_index("pass_chunk_unknown") is None


def test_prompt_mapper_separate_instances_zero_collision():
    passage_mapper = PromptIdMapper(prefix="passage")
    concept_mapper = PromptIdMapper(prefix="concept")

    p_idx = passage_mapper.register("pass_001")
    c_idx = concept_mapper.register("concept_alpha")

    # Both start at 1
    assert p_idx == 1
    assert c_idx == 1

    # But each resolves to its own domain ID
    assert passage_mapper.to_id(1) == "pass_001"
    assert concept_mapper.to_id(1) == "concept_alpha"

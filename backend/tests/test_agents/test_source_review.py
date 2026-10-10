import pytest

from tests.evaluation_v2.source_review import map_answer_to_context


def test_delivered_citation_is_resolved_by_chunk_not_original_position():
    sources = [{"index": 1, "document_id": "petrol", "chunk_id": "old"},
               {"index": 2, "document_id": "ev-policy", "chunk_id": "new"}]
    response = {"citations": [{"document_id": "ev-policy", "chunk_id": "new"}],
                "metadata": {"source_cited_doc_indexes": [2]}}
    answer, mapping = map_answer_to_context("15.000 km [Tài liệu 1].", response, sources)
    assert answer == "15.000 km [Tài liệu 2]." and mapping == {1: 2}


def test_mapping_does_not_replace_numbers_twice_or_change_claim():
    sources = [{"index": i, "document_id": "doc", "chunk_id": str(i)} for i in (1, 2, 3)]
    response = {"citations": [{"document_id": "doc", "chunk_id": "2"}, {"document_id": "doc", "chunk_id": "3"}]}
    answer, _ = map_answer_to_context("2 năm [Tài liệu 1] [Tài liệu 2].", response, sources)
    assert answer == "2 năm [Tài liệu 2] [Tài liệu 3]."


def test_mismatched_metadata_and_missing_reference_fail_closed():
    sources = [{"index": 2, "document_id": "doc", "chunk_id": "chunk"}]
    citation = {"document_id": "doc", "chunk_id": "chunk"}
    with pytest.raises(ValueError, match="disagrees"):
        map_answer_to_context("Text [Tài liệu 1].", {"citations": [citation], "metadata": {"source_cited_doc_indexes": [1]}}, sources)
    with pytest.raises(ValueError, match="missing"):
        map_answer_to_context("Text [Tài liệu 2].", {"citations": [citation]}, sources)

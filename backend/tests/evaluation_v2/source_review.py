"""Map delivered citation numbers to frozen context by immutable chunk identity."""
from __future__ import annotations

import re


def map_answer_to_context(answer: str, response: dict, sources: list[dict]) -> tuple[str, dict[int, int]]:
    mapping = {}
    for final_index, citation in enumerate(response.get("citations", []), 1):
        matches = [source for source in sources if source["chunk_id"] == citation["chunk_id"]
                   and source["document_id"] == citation["document_id"]]
        if len(matches) != 1:
            raise ValueError("Citation must identify exactly one frozen source chunk")
        mapping[final_index] = matches[0]["index"]
    declared = response.get("metadata", {}).get("source_cited_doc_indexes")
    if declared is not None and list(mapping.values()) != declared:
        raise ValueError("Saved source-index metadata disagrees with final citation identity")
    references = {int(number) for number in re.findall(r"\[Tài liệu\s+(\d+)\]", answer)}
    if references - mapping.keys():
        raise ValueError("Delivered answer references a missing final citation")
    result = re.sub(r"\[Tài liệu\s+(\d+)\]", lambda match: f"[Tài liệu {mapping[int(match[1])]}]", answer)
    return result, mapping

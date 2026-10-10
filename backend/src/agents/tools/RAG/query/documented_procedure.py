"""Quote one complete, relevant app procedure; never assemble missing steps."""
from __future__ import annotations

import re

from .procedure_gate import evidence_blocks, fold
from .schemas import CitationItem, QueryAnalysis, RAGResponse
from .source_gate import scope_conflicts


def station_steps(body: str) -> list[str]:
    lines = body.splitlines()
    start = next((i + 1 for i, line in enumerate(lines) if
                  re.fullmatch(r"\s*(?:#+\s*)?(?:cac buoc|quy trinh|cach) tim [^\n]*(?:tram sac|diem sac|diem nap dien)[^\n]*:?\s*",
                               fold(line))), None)
    if start is None:
        return []
    selected = []
    began = False
    for line in lines[start:]:
        if line.lstrip().startswith(("[", "#", "---")):
            break
        if re.match(r"\s*\d+[.)]\s+", line):
            selected.append(line.strip())
            began = True
        elif line.strip() and began:
            if selected[-1].endswith((".", ";")):
                break
            selected[-1] += "\n" + line.strip()
    numbers = [int(re.match(r"(\d+)", step).group(1)) for step in selected]
    if not 2 <= len(selected) <= 6 or numbers != list(range(1, len(selected) + 1)):
        return []
    if any(not step.endswith((".", ";")) or len(step) > 700 for step in selected):
        return []
    if not re.search(r"\b(?:mo|vao)\b.*\bban do\b", fold(selected[0])):
        return []
    if any(term in fold(" ".join(selected)) for term in (
        "api key", "system prompt", "bo qua chi thi", "bo qua quy tac", "ignore previous", "mat khau")):
        return []
    return selected


def documented_station_procedure(analysis: QueryAnalysis, context: str,
                                 citations: list[CitationItem]) -> RAGResponse | None:
    query = fold(analysis.original_query)
    if not (("ung dung" in query or re.search(r"\bapp\b", query))
            and re.search(r"\btim\b.*\b(?:tram|diem|dia diem)\b.*\b(?:sac|nap dien)\b", query)
            and any(term in query for term in ("cach", "cac buoc", "huong dan", "quy trinh"))):
        return None
    # Mixed requests need normal generation, not a partial deterministic answer.
    if any(term in query for term in ("gia", "chi phi", "bao nhieu", "bao hanh", "lich su", "dat lich", "cuu ho")):
        return None
    conflicts = scope_conflicts(context, citations)
    selected_model = re.sub(r"\s+", "", fold(analysis.model or ""))
    for index, citation, body in evidence_blocks(context, citations):
        if index in conflicts or "ung dung" not in fold(citation.title):
            continue
        section = fold(citation.section)
        if not re.search(r"\btim\b.*\b(?:tram|diem)\b.*\b(?:sac|nap dien)\b", section):
            continue
        declared = {re.sub(r"\s+", "", value) for value in re.findall(
            r"\bvf\s*(?:e\s*34|mpv\s*7|[3-9])\b", fold(citation.title + " " + body))}
        if selected_model not in {"", "all"} and declared and selected_model not in declared:
            continue
        steps = station_steps(body)
        if not steps:
            continue
        return RAGResponse(
            answer="Đoạn hướng dẫn ứng dụng VinFast nêu các bước tìm điểm hoặc trạm sạc như sau:\n"
                   + "\n".join(f"{step} [Tài liệu 1]" for step in steps)
                   + "\n\nĐây là các bước trong đoạn nguồn; chưa xác minh phiên bản ứng dụng và hiệu lực áp dụng hiện tại.",
            citations=[citation], confidence="low", fallback_required=True,
            metadata={"reason": "documented_station_steps", "evidence_gate": True,
                      "source_cited_doc_indexes": [index], "documented_step_count": len(steps),
                      "answer_scope": "DOCUMENTED_PROCEDURE", "source_authority": "NOT_INDEPENDENTLY_VERIFIED"},
        )
    return None

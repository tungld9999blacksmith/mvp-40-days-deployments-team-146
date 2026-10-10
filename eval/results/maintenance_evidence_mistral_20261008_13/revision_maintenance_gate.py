"""Preserve literal evidence when maintenance table columns are incomplete.

These checks do not repair source documents or certify current maintenance rules.
Only observed ragged period tables for the explicitly requested model qualify.
"""
from __future__ import annotations

import re

from .procedure_gate import evidence_blocks, fold
from .schemas import CitationItem, QueryAnalysis, RAGResponse
from .source_gate import scope_conflicts

MODEL = r"vf\s*(?:e\s*34|mpv\s*7|[3-9])\b"


def table_rows(body: str) -> list[list[str]]:
    # Retain empty cells: a row with correctly aligned blank actions is different
    # from a row whose columns were lost entirely during extraction.
    return [line.strip().strip("|").split("|") for line in body.splitlines() if line.strip().startswith("|")]


def ragged_period_table(body: str) -> bool:
    rows = [[cell.strip() for cell in row] for row in table_rows(body)]
    headers = [row for row in rows if "km hoac thang tuong ung" in fold(row[0]) and len(row) > 2]
    return bool(headers and any(len(row) < len(headers[0]) for row in rows if row and fold(row[0]) in {"dau phanh", "pin", "cong sac", "nuoc lam mat pin/dong co dien"}))


def maintenance_evidence_gate(analysis: QueryAnalysis, context: str, citations: list[CitationItem]) -> RAGResponse | None:
    query = fold(analysis.original_query)
    models = {re.sub(r"\s+", "", m) for m in re.findall(MODEL, query)}
    if len(models) != 1 or not any(term in query for term in ["bao duong", "dinh ky", "can thay"]):
        return None
    model = next(iter(models))
    conflicts = scope_conflicts(context, citations)
    tables = [(i, c, body) for i, c, body in evidence_blocks(context, citations) if i not in conflicts and model in {re.sub(r"\s+", "", m) for m in re.findall(MODEL, fold(c.title + " " + c.section))} and ragged_period_table(body)]
    if not tables:
        return None

    coolant = any(term in query for term in ["nuoc lam mat", "chat lam mat", "dung dich lam mat", "coolant"])
    if coolant:
        suspicious = [(i, c, row) for i, c, body in tables for row in table_rows(body) if len(row) == 2 and "nuoc lam mat pin/dong co dien" in fold(row[0]) and re.search(r"thang thu\s+120\s+hoac sau\s+12[.,]000\s*km\b", fold(row[1]))]
        if suspicious:
            i, c, row = suspicious[0]
            quote = row[0].strip() + ": " + row[1].strip()
            return RAGResponse(
                answer=f'Bảng được cung cấp ghi: “{quote}” [Tài liệu 1].\n\nMốc thay trong dòng này chưa được xác minh với bảng gốc đầy đủ và phiên bản áp dụng. Tôi chưa thể chốt lịch thay cho xe từ bản trích này; không tự sửa số km trong nguồn hoặc ngoại suy chu kỳ. Cần đối chiếu đúng lịch bảo dưỡng trước khi áp dụng.',
                citations=[c], confidence="low", fallback_required=True,
                metadata={"reason": "coolant_source_value_unverified", "evidence_gate": True, "source_cited_doc_indexes": [i], "literal_source_row": quote, "source_rule_verified": False},
            )

    component_list = "pin cao ap" in query and "cong sac" in query and "hang muc" in query
    if component_list:
        for i, c, body in tables:
            rows = [[cell.strip() for cell in row] for row in table_rows(body)]
            labels = [row[0] for row in rows if fold(row[0]) in {"pin", "day cap cua he thong dien ap cao", "cong sac"}]
            empty = [row[0] for row in rows if fold(row[0]) in {"pin", "day cap cua he thong dien ap cao", "cong sac"} and (len(row) == 1 or not any(row[1:]))]
            if len(set(labels)) < 3 or set(empty) != set(labels):
                continue
            quoted = ", ".join(f'“{label}”' for label in labels)
            coolant_labels = [row[0] for row in rows if "nuoc lam mat pin/dong co dien" in fold(row[0])]
            coolant_note = f'\n\nBảng cũng nêu “{coolant_labels[0]}” [Tài liệu 1], nhưng mốc thay của dòng này cần xác minh với bảng gốc.' if coolant_labels else ""
            return RAGResponse(
                answer=f'Bảng liệt kê các hạng mục {quoted} [Tài liệu 1]. Tuy nhiên, các dòng này trong bản trích không có thao tác hoặc chu kỳ đi kèm; chưa thể kết luận chúng đều phải kiểm tra định kỳ theo lịch cụ thể.{coolant_note}\n\nCần lịch đầy đủ, đúng phiên bản để xác định thao tác và thời điểm cho từng hạng mục.',
                citations=[c], confidence="low", fallback_required=True,
                metadata={"reason": "maintenance_component_actions_missing", "evidence_gate": True, "source_cited_doc_indexes": [i], "literal_component_labels": labels, "source_rule_verified": False},
            )

    amounts = re.findall(r"(?<![\w.,])(\d+(?:[.,]\d{3})*)\s*km\b", query)
    replace_list = re.search(r"\bthay\b", query) and any(term in query for term in ["phu tung", "hang muc"])
    if replace_list and len(amounts) == 1:
        # A direct rule or a complete period matrix must still reach generation.
        amount = amounts[0]
        number = int(amount.replace(".", "").replace(",", ""))
        relevant = [(i, c, body) for i, c, body in evidence_blocks(context, citations) if i not in conflicts and model in {re.sub(r"\s+", "", m) for m in re.findall(MODEL, fold(c.title + " " + c.section))}]
        for _, _, body in relevant:
            for sentence in re.split(r"\n|(?<=[.!?])\s+", body):
                text = fold(sentence)
                explicit = re.findall(r"(?<![\w.,])(\d+(?:[.,]\d{3})*)\s*km\b", text)
                if "thay" in text and any(int(n.replace(".", "").replace(",", "")) == number for n in explicit) and "bao hanh" not in text:
                    return None
            if table_rows(body) and not ragged_period_table(body):
                return None
        i, c, _ = tables[0]
        return RAGResponse(
            answer=f'Chưa xác định được danh sách phụ tùng bắt buộc thay tại mốc {amount} km từ các đoạn được cung cấp. Bảng có các mốc km/tháng nhưng các dòng hạng mục thiếu cột thao tác tương ứng [Tài liệu 1].\n\nKhông dùng các dòng đã mất ánh xạ để suy ra thao tác tại mốc bạn hỏi. Cần bảng đầy đủ, đúng dòng xe và phiên bản; không áp toàn bộ danh sách thay thế vào mốc này.',
            citations=[c], confidence="low", fallback_required=True,
            metadata={"reason": "maintenance_period_mapping_missing", "evidence_gate": True, "source_cited_doc_indexes": [i], "requested_milestone_km": number, "source_rule_verified": False},
        )
    return None

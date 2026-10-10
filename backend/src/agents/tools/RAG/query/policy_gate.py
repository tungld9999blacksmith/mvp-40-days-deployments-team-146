"""Narrow source-relative policy checks; no current-policy certification."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .procedure_gate import evidence_blocks, fold
from .schemas import CitationItem, QueryAnalysis, RAGResponse
from .source_gate import scope_conflicts


def visible_text(value: str) -> str:
    """Classify rendered words; keep the delivered/raw source text intact."""
    return " ".join(re.sub(r"[*_`]", "", fold(value)).split())


def vehicle_expiry_gate(analysis: QueryAnalysis, context: str, citations: list[CitationItem]) -> RAGResponse | None:
    query = fold(analysis.original_query)
    models = set(re.findall(r"\bvf\s*[3-9]\b", query))
    ages = re.findall(r"\b(\d+)\s*nam\b", query)
    if (len(models) != 1 or len(ages) != 1 or "bao hanh" not in query
            or not re.search(r"\b(?:con|het)\b", query)
            or re.search(r"\b(?:pin|ac quy|gi set|son|lop)\b", query)
            or re.search(r"\b(?:chua|duoi|khong phai|hoac|hay)\b", query)):
        return None
    selected = re.sub(r"\s+", "", next(iter(models)))
    conflicts = scope_conflicts(context, citations)
    rules = []
    for index, citation, body in evidence_blocks(context, citations):
        if index in conflicts:
            continue
        text = fold(" ".join(body.split()))
        for match in re.finditer(
            r"thoi han bao hanh chung doi voi (?:xe )?(vf\s*[3-9]) la (\d+) nam ke tu ngay kich hoat bao hanh hoac ([\d.,]+)\s*km tuy (?:thuoc vao )?dieu kien nao den truoc",
            text,
        ):
            if re.sub(r"\s+", "", match[1]) == selected:
                rules.append((index, citation, int(match[2]), match[3], text[match.end():]))
    if not rules or len({(r[2], r[3]) for r in rules}) != 1:
        return None  # Conflicting/partial policy evidence must not become certainty.
    index, citation, years, distance, tail = rules[0]
    if int(ages[0]) < years:
        return None  # Time below a limit does not establish warranty eligibility.
    answer = (
        f"Điều khoản được trích cho {selected.upper()} giới hạn bảo hành xe ở {years} năm kể từ Ngày Kích Hoạt Bảo Hành hoặc {distance} km, tùy điều kiện nào đến trước [Tài liệu 1].\n\n"
        f"Nếu đã đủ {years} năm kể từ ngày kích hoạt, bảo hành xe theo điều khoản này đã hết giới hạn thời gian, dù chưa đạt {distance} km [Tài liệu 1]."
    )
    # Keep this exception within the vehicle section; battery/rust terms cannot
    # supply a commercial vehicle duration.
    vehicle_tail = re.split(r"\b6\.\s*phu tung|\bpin\s*\(", tail)[0]
    commercial = re.search(
        r"trong truong hop[^.]{0,1200}?dich vu thuong mai[^.]{0,1200}?thoi han bao hanh la (\d+) nam ke tu ngay kich hoat bao hanh hoac ([\d.,]+)\s*km tuy (?:thuoc vao )?dieu kien nao den truoc",
        vehicle_tail,
    )
    if commercial:
        answer += f"\n\nCùng đoạn nguồn nêu xe dùng cho dịch vụ thương mại có giới hạn {commercial[1]} năm hoặc {commercial[2]} km, tùy điều kiện nào đến trước [Tài liệu 1]."
    answer += "\n\nĐể kiểm tra xe cụ thể, cần ngày kích hoạt bảo hành, ODO và mục đích sử dụng. Kết luận trên chỉ áp dụng cho bảo hành xe theo điều khoản được trích."
    return RAGResponse(
        answer=answer, citations=[citation], confidence="medium", fallback_required=False,
        metadata={"reason": "vehicle_warranty_elapsed_limit", "evidence_gate": True,
                  "source_cited_doc_indexes": [index], "warranty_years": years,
                  "warranty_km": distance, "user_age_years": int(ages[0]),
                  "vehicle_eligibility_verified": False},
    )


@dataclass(frozen=True)
class FollowupRule:
    index: int
    citation: CitationItem
    sentence: str
    days: int


def followup_rules(context: str, citations: list[CitationItem]) -> list[FollowupRule]:
    conflicts = scope_conflicts(context, citations)
    rules = []
    for index, citation, body in evidence_blocks(context, citations):
        if index in conflicts:
            continue
        body = re.sub(r"^\[[^\n]*\]\s*$", "", body, flags=re.MULTILINE)
        for sentence in re.split(r"(?<=[.!?])\s+", " ".join(body.split())):
            text = visible_text(sentence)
            values = re.findall(r"trong vong (\d+) ngay sau khi", text)
            if (len(values) == 1 and len(sentence) < 400 and "goi dien" in text
                    and re.search(r"ghi nhan (?:phan hoi|y kien)", text)
                    and not re.search(r"\b(?:neu|doi voi|rieng|thuong mai|ca nhan|mobile service)\b", text)
                    and ("bao duong" in text or "xe ra xuong" in text)):
                rule = FollowupRule(index, citation, sentence.strip(), int(values[0]))
                if not any(r.index == rule.index and r.days == rule.days for r in rules):
                    rules.append(rule)
    return rules


def followup_conflict_repair(analysis: QueryAnalysis, context: str, citations: list[CitationItem], answer: str) -> tuple[str, list[int], dict] | None:
    """Keep the rest of a workflow; replace only source-disputed call deadlines."""
    query = fold(analysis.original_query)
    if not re.search(r"\b(?:bao duong|cham soc|phan hoi|goi dien)\b", query):
        return None
    rules = followup_rules(context, citations)
    if len({r.days for r in rules}) < 2 or len({r.index for r in rules}) < 2:
        return None
    # Do not add post-service details to an unrelated answer just because they
    # happened to be retrieved. A direct followup question still needs both sources.
    answer_text = visible_text(answer)
    if "goi dien" not in answer_text and not re.search(r"\b(?:cham soc|phan hoi|goi dien)\b", query):
        return None
    disputed_days = {r.days for r in rules}
    removed = []

    def replace(match):
        sentence = match.group(0)
        text = visible_text(sentence)
        words = {"mot": 1, "hai": 2, "ba": 3, "bon": 4, "nam": 5}
        values = {
            int(value) if value.isdigit() else words[value]
            for pair in re.findall(r"\b(\d+|mot|hai|ba|bon|nam)(?:\s*(?:[-–/]|den|hoac)\s*(\d+|mot|hai|ba|bon|nam))?\s*ngay\b", text)
            for value in pair if value
        }
        if (values & disputed_days and "ngay" in text and "goi dien" in text
                and re.search(r"\b(?:phan hoi|y kien)\b", text)):
            removed.append(sentence.strip())
            return ""
        return sentence

    repaired = re.sub(r"[^.!?\n]+(?:[.!?]|$)", replace, answer)
    quotes = "\n".join(f'- “{rule.sentence}” [Tài liệu {rule.index}]' for rule in rules)
    repaired = repaired.rstrip() + "\n\nCác đoạn nguồn nêu mốc chăm sóc sau dịch vụ khác nhau:\n" + quotes
    repaired += "\nChưa xác minh được phiên bản/phạm vi đang áp dụng để chọn một mốc chung. Không gộp các mốc này thành một khoảng thời gian cam kết; cần xưởng hoặc chủ nguồn xác nhận."
    return repaired, sorted({r.index for r in rules}), {
        "reason": "post_service_followup_source_disagreement", "evidence_gate": True,
        "original_generation_answer": answer, "removed_followup_claims": removed,
        "source_followup_rules": [{"original_index": r.index, "days": r.days, "sentence": r.sentence} for r in rules],
    }

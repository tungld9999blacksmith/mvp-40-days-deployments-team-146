from __future__ import annotations

import json
import logging
import re
from typing import Any

try:
    from src.infrastructure.llm.base import ChatMessage, GenerationConfig, LLMProvider  # type: ignore
except ImportError:
    from infrastructure.llm.base import ChatMessage, GenerationConfig, LLMProvider  # type: ignore

from src.infrastructure.prompts import load_prompt

from .answer_scope import is_evidence_limitation
from .documented_procedure import documented_station_procedure
from .maintenance_gate import maintenance_evidence_gate
from .policy_gate import followup_conflict_repair, vehicle_expiry_gate
from .procedure_gate import procedure_evidence_gate
from .schemas import CitationItem, GroundedAnswerPayload, QueryAnalysis, RAGResponse, UserVehicleContext
from .source_gate import scope_conflicts, scope_fallback, source_evidence_gate

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = load_prompt("rag_generator")


class GroundedAnswerGenerator:
    """Sinh câu trả lời Grounded có trích dẫn nguồn chuẩn xác, tuân thủ nghiêm ngặt schema JSON."""

    def __init__(self, llm_provider: LLMProvider | None = None) -> None:
        self._llm_provider = llm_provider

    @property
    def llm_provider(self) -> LLMProvider | None:
        if self._llm_provider is None:
            try:
                try:
                    from src.infrastructure.llm.dependency import get_llm_provider_for_stage
                except ImportError:
                    from infrastructure.llm.dependency import get_llm_provider_for_stage  # type: ignore

                self._llm_provider = get_llm_provider_for_stage("rag")
            except Exception as e:
                logger.debug(f"Không thể khởi tạo LLMProvider tự động trong generator: {e}")
                return None
        return self._llm_provider

    async def generate(
        self,
        query_analysis: QueryAnalysis,
        context_text: str,
        citations: list[CitationItem],
        vehicle_context: UserVehicleContext | None = None,
    ) -> RAGResponse:
        """Sinh câu trả lời từ Context và trích dẫn chuẩn."""
        # 1. Kiểm tra trường hợp ngoài phạm vi (Out of Scope)
        if query_analysis.is_out_of_scope:
            return RAGResponse(
                answer="Xin lỗi, tôi là trợ lý kỹ thuật chuyên trách về dịch vụ và bảo dưỡng xe điện VinFast. Câu hỏi của bạn nằm ngoài phạm vi hỗ trợ.",
                citations=[],
                confidence="low",
                fallback_required=True,
                metadata={"reason": "out_of_scope"},
            )

        # 2. Kiểm tra trường hợp không tìm thấy tài liệu phù hợp
        if not citations:
            model_info = f" cho dòng xe {query_analysis.model}" if query_analysis.model else ""
            return RAGResponse(
                answer=f"Hiện hệ thống chưa tìm thấy tài liệu kỹ thuật chính hãng phù hợp{model_info} để giải đáp câu hỏi của bạn. Vui lòng liên hệ xưởng dịch vụ hoặc đặt lịch tư vấn trực tiếp với kỹ thuật viên.",
                citations=[],
                confidence="low",
                fallback_required=True,
                metadata={"reason": "no_documents_found"},
            )

        # 3. Chuẩn bị prompt gửi tới LLM
        evidence_check = source_evidence_gate(query_analysis, context_text, citations) or documented_station_procedure(query_analysis, context_text, citations) or procedure_evidence_gate(query_analysis, context_text, citations) or maintenance_evidence_gate(query_analysis, context_text, citations, vehicle_context) or vehicle_expiry_gate(query_analysis, context_text, citations)
        if evidence_check is not None:
            return evidence_check
        messages = self.build_messages(query_analysis, context_text, vehicle_context)

        provider = self.llm_provider
        if provider is None:
            # Fallback nếu không có LLM Provider
            return self._build_offline_response(citations)

        try:
            extra = {}
            if getattr(provider, "provider_name", None) in {"openrouter", "openai"}:
                extra["response_format"] = {"type": "json_schema", "json_schema": {"name": "grounded_answer", "strict": True, "schema": GroundedAnswerPayload.model_json_schema()}}
                if provider.provider_name == "openrouter":
                    extra["extra_body"] = {"provider": {"require_parameters": True}}
            response = await provider.chat(
                messages=messages,
                config=GenerationConfig(temperature=0.1, max_tokens=3000, extra=extra),
            )
            if response.stop_reason == "error":
                raise RuntimeError("LLM provider signaled finish_reason=error")

            raw_text = response.text.strip()
            parsed_json = self._extract_json(raw_text)
            if extra:
                parsed_json = GroundedAnswerPayload.model_validate(parsed_json, strict=True).model_dump()

            answer = self._normalize_citation_tags(parsed_json.get("answer", ""))
            confidence = parsed_json.get("confidence", "high")
            if confidence not in {"high", "medium", "low"}:
                confidence = "low"
            fallback_required = bool(parsed_json.get("fallback_required", False))
            cited_indexes = parsed_json.get("cited_doc_indexes", [])

            # A model may cite a mismatched model chunk even when other valid
            # sources are present. Preserve its raw output but reject that answer.
            conflicts = scope_conflicts(context_text, citations)
            referenced = {int(i) for i in re.findall(r"\[Tài liệu\s+(\d+)\]", answer)} | {i for i in cited_indexes if type(i) is int}
            if referenced.intersection(conflicts):
                return scope_fallback(conflicts, original_answer=answer)

            policy_metadata = {}
            repaired = followup_conflict_repair(query_analysis, context_text, citations, answer)
            if repaired:
                answer, needed_indexes, policy_metadata = repaired
                cited_indexes = sorted(set(cited_indexes) | set(needed_indexes))
                confidence, fallback_required = "low", True

            # Chỉ giữ citation vừa được khai báo trong JSON vừa xuất hiện trong
            # answer. Bản cũ trả toàn bộ retrieved citations khi model quên
            # index, khiến citation correctness thực tế giảm mạnh.
            final_citations, valid_indexes = self._resolve_citations(
                answer=answer,
                cited_indexes=cited_indexes,
                citations=citations,
            )
            # Renumber retained sources and remove every unsupported tag,
            # including when a fallback answer has no valid sources.
            index_map = {old: new for new, old in enumerate(valid_indexes, 1)}
            answer = re.sub(
                r"\[Tài liệu\s+(\d+)\]",
                lambda match: (
                    f"[Tài liệu {index_map[int(match.group(1))]}]"
                    if int(match.group(1)) in index_map
                    else ""
                ),
                answer,
                flags=re.IGNORECASE,
            )
            limitation_only = is_evidence_limitation(answer)
            has_claim = bool(answer.strip()) and not limitation_only
            if has_claim and not final_citations:
                policy_metadata["original_uncited_answer"] = answer
                policy_metadata["reason"] = "uncited_content_rejected"
                fallback_required = True
                confidence = "low"
                answer = (
                    "Các đoạn tài liệu được cung cấp chưa xác định đủ bằng chứng trực tiếp cho nội dung được hỏi."
                )
                limitation_only = True

            return RAGResponse(
                answer=answer,
                citations=final_citations,
                confidence=confidence,
                fallback_required=fallback_required,
                metadata={
                    **policy_metadata,
                    "model": response.model,
                    "rewritten_query": query_analysis.rewritten_query,
                    "source_cited_doc_indexes": valid_indexes,
                    "answer_scope": "EVIDENCE_LIMITATION" if limitation_only else "GENERATED_CONTENT",
                },
            )
        except Exception as e:
            logger.error(f"Lỗi khi gọi LLM sinh câu trả lời Grounded: {e}")
            return self._build_offline_response(citations)

    @staticmethod
    def build_messages(
        query_analysis: QueryAnalysis,
        context_text: str,
        vehicle_context: UserVehicleContext | None = None,
    ) -> list[ChatMessage]:
        """Rewrite is a retrieval hint, not an additional factual user instruction."""
        lines = [f'CÂU HỎI GỐC CỦA NGƯỜI DÙNG: "{query_analysis.original_query}"']
        if vehicle_context and vehicle_context.model:
            odo = vehicle_context.current_odometer_km
            lines.append(f"THÔNG TIN XE NGƯỜI DÙNG: {vehicle_context.model} (ODO: {odo if odo is not None else 'N/A'} km)")
        lines.append("\n" + context_text)
        return [ChatMessage(role="system", content=SYSTEM_PROMPT), ChatMessage(role="user", content="\n".join(lines))]

    @staticmethod
    def _normalize_citation_tags(answer: str) -> str:
        """Expand grouped references before checking declared source indexes."""
        return re.sub(
            r"\[Tài liệu\s+\d+(?:(?:\s*[,;]\s*|\s+và\s+)(?:Tài liệu\s+)?\d+)+\s*\]",
            lambda match: " ".join(
                f"[Tài liệu {int(index)}]" for index in re.findall(r"\d+", match.group(0))
            ),
            answer,
            flags=re.IGNORECASE,
        )

    def _resolve_citations(
        self,
        answer: str,
        cited_indexes: Any,
        citations: list[CitationItem],
    ) -> tuple[list[CitationItem], list[int]]:
        """Đối chiếu citation JSON với các thẻ thực sự có trong câu trả lời."""
        answer_indexes = {
            int(value)
            for value in re.findall(r"\[Tài liệu\s+(\d+)\]", answer, flags=re.IGNORECASE)
        }
        declared_indexes = {
            index
            for index in cited_indexes
            if type(index) is int
        } if isinstance(cited_indexes, list) else set()
        valid_indexes = sorted(
            index
            for index in answer_indexes & declared_indexes
            if 1 <= index <= len(citations)
        )
        return [citations[index - 1] for index in valid_indexes], valid_indexes

    def _extract_json(self, text: str) -> dict[str, Any]:
        """Trích xuất JSON an toàn từ LLM."""
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            text = text.strip()

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(text)

    def _build_offline_response(self, citations: list[CitationItem]) -> RAGResponse:
        """Sinh câu trả lời tóm tắt ngoại tuyến khi không thể kết nối LLM."""
        lines = [
            "Hiện không thể kết nối AI để tổng hợp câu trả lời. Các tài liệu liên quan đã tìm thấy:",
        ]
        for idx, c in enumerate(citations[:3], 1):
            lines.append(
                f"- [{idx}] {c.title} ({c.section or 'Thông tin chung'}): Vui lòng tham khảo tài liệu [Tài liệu {idx}]."
            )

        # Answer text chỉ reference 3 citations đầu, nên response cũng chỉ trả 3
        offline_citations = citations[:3]
        return RAGResponse(
            answer="\n".join(lines),
            citations=offline_citations,
            confidence="low",
            fallback_required=True,
            metadata={"mode": "offline_summary", "reason": "answer_generation_unavailable"},
        )

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from src.infrastructure.llm.base import ChatMessage, GenerationConfig, LLMProvider

from .schemas import QueryAnalysis, UserVehicleContext

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Bạn là Chuyên gia Kỹ thuật và Phân tích Truy vấn cho Hệ thống Chăm sóc Sau bán hàng Xe điện VinFast (EV Care).
Nhiệm vụ của bạn là nhận câu hỏi thô của người dùng (kèm thông tin xe nếu có), sau đó:
1. Viết lại câu hỏi (Rewritten Query) rõ ràng, đầy đủ ngữ cảnh, loại bỏ đại từ mơ hồ ("xe tôi", "nó", "xe này"), chuẩn hóa thuật ngữ kỹ thuật xe điện.
2. Trích xuất danh sách từ khóa cốt lõi (Keywords) phục vụ thuật toán tìm kiếm từ vựng BM25.
3. Trích xuất các trường Metadata Filter:
   - model: Mã dòng xe cụ thể (VF3, VF5, VF6, VF7, VF8, VF9, VFe34, VFMPV7, Evo200, Feliz, Klara, Vento, Theon). Nếu câu hỏi áp dụng chung cho mọi xe hoặc không xác định được dòng xe, trả về "ALL".
   - category: Phân loại chính xác nhất trong các nhóm:
     + "maintenance": Lịch bảo dưỡng định kỳ, hạng mục kiểm tra theo km/thời gian, thay phụ tùng định kỳ.
     + "warranty": Chính sách bảo hành, thời hạn, số km bảo hành, điều kiện từ chối bảo hành.
     + "pricing": Bảng giá phụ tùng, chi phí nhân công, dự toán bảo dưỡng.
     + "battery": Pin cao áp, pin 12V, sạc pin, an toàn pin, dung lượng pin (SoH).
     + "procedure": Quy trình đặt lịch, quy trình tiếp nhận, duyệt báo giá tại xưởng.
     + "safety": Cảnh báo nguy hiểm, xử lý sự cố khẩn cấp, cứu hộ.
     + "general": Các câu hỏi chung khác.
   - milestone_km: Số nguyên chỉ mốc km bảo dưỡng (ví dụ: 12000, 15000, 24000, 30000, 48000). Nếu không có, trả về null.
   - subsystem: Bộ phận liên quan (battery, charging, motor, brake, hvac, software, chassis). Nếu không có, trả về null.
   - is_out_of_scope: true nếu câu hỏi hoàn toàn không liên quan đến xe điện, xe cộ, bảo dưỡng hoặc dịch vụ (ví dụ: hỏi thời tiết, nấu ăn, chứng khoán...). Ngược lại trả về false.

BẮT BUỘC trả về đúng định dạng JSON thuần túy (không kèm giải thích bên ngoài), theo schema:
{
  "rewritten_query": "string",
  "keywords": ["string", "string"],
  "model": "string hoặc null",
  "category": "string hoặc null",
  "milestone_km": integer hoặc null,
  "subsystem": "string hoặc null",
  "is_out_of_scope": boolean
}
"""

ALL_KNOWN_MODELS = [
    "VFe34",
    "VFMPV7",
    "VF3",
    "VF5",
    "VF6",
    "VF7",
    "VF8",
    "VF9",
    "Evo200",
    "Feliz",
    "Klara",
    "Vento",
    "Theon",
]


class QueryRewriter:
    """Module Bước 1: Viết lại query và trích xuất bộ lọc metadata bằng LLM."""

    def __init__(self, llm_provider: LLMProvider | None = None) -> None:
        self._llm_provider = llm_provider

    @property
    def llm_provider(self) -> LLMProvider | None:
        if self._llm_provider is None:
            try:
                from src.infrastructure.llm.dependency import get_llm_provider

                self._llm_provider = get_llm_provider()
            except Exception as e:
                logger.debug(f"Không thể khởi tạo LLMProvider tự động: {e}. Sẽ dùng fallback nếu cần.")
                return None
        return self._llm_provider

    async def analyze(
        self,
        query: str,
        vehicle_context: UserVehicleContext | None = None,
    ) -> QueryAnalysis:
        """Phân tích và trích xuất metadata từ câu hỏi."""
        cleaned_query = query.strip()
        if not cleaned_query:
            return QueryAnalysis(
                original_query="",
                rewritten_query="",
                keywords=[],
                model=None,
                category=None,
                is_out_of_scope=True,
            )

        provider = self.llm_provider
        if provider is None:
            return self._heuristic_fallback(cleaned_query, vehicle_context)

        # Xây dựng prompt người dùng kèm ngữ cảnh xe
        user_prompt_lines = [f"Câu hỏi của người dùng: \"{cleaned_query}\""]
        if vehicle_context:
            context_desc = []
            if vehicle_context.model:
                context_desc.append(f"Dòng xe người dùng sở hữu: {vehicle_context.model}")
            if vehicle_context.current_odometer_km:
                context_desc.append(f"Số ODO hiện tại: {vehicle_context.current_odometer_km:,} km")
            if vehicle_context.battery_type:
                context_desc.append(f"Loại pin: {vehicle_context.battery_type}")
            if context_desc:
                user_prompt_lines.append(f"Ngữ cảnh xe hiện tại của người dùng: ({'; '.join(context_desc)})")

        user_content = "\n".join(user_prompt_lines)

        try:
            response = await provider.chat(
                messages=[
                    ChatMessage(role="system", content=SYSTEM_PROMPT),
                    ChatMessage(role="user", content=user_content),
                ],
                config=GenerationConfig(temperature=0.0, max_tokens=500),
            )
            raw_text = response.text.strip()
            parsed_json = self._extract_json(raw_text)

            return QueryAnalysis(
                original_query=cleaned_query,
                rewritten_query=parsed_json.get("rewritten_query") or cleaned_query,
                keywords=parsed_json.get("keywords") or self._fallback_keywords(cleaned_query),
                model=parsed_json.get("model") or (vehicle_context.model if vehicle_context else None),
                category=parsed_json.get("category"),
                milestone_km=parsed_json.get("milestone_km"),
                subsystem=parsed_json.get("subsystem"),
                is_out_of_scope=bool(parsed_json.get("is_out_of_scope", False)),
            )
        except Exception as e:
            logger.warning(f"Lỗi khi gọi LLM QueryRewriter: {e}. Áp dụng fallback heuristic.")
            return self._heuristic_fallback(cleaned_query, vehicle_context)

    def analyze_sync(
        self,
        query: str,
        vehicle_context: UserVehicleContext | None = None,
    ) -> QueryAnalysis:
        """Hàm đồng bộ (synchronous wrapper) phục vụ script kiểm thử."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import nest_asyncio  # type: ignore

            nest_asyncio.apply()
            return loop.run_until_complete(self.analyze(query, vehicle_context))
        else:
            return asyncio.run(self.analyze(query, vehicle_context))

    def _extract_json(self, text: str) -> dict[str, Any]:
        """Bóc tách JSON an toàn từ phản hồi LLM."""
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            text = text.strip()

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(text)

    def _heuristic_fallback(
        self,
        query: str,
        vehicle_context: UserVehicleContext | None = None,
    ) -> QueryAnalysis:
        """Cơ chế dự phòng bằng luật nếu LLM provider gặp sự cố hoặc timeout."""
        lower = query.lower()

        # 1. Phát hiện Model
        found_model = None
        for m in ALL_KNOWN_MODELS:
            if m.lower() in lower:
                found_model = m
                break
        if not found_model and vehicle_context and vehicle_context.model:
            found_model = vehicle_context.model

        # 2. Phát hiện Category
        if any(w in lower for w in ["giá", "bảng giá", "chi phí", "tiền công", "hết bao nhiêu"]):
            category = "pricing"
        elif any(w in lower for w in ["bảo hành", "sổ bảo hành", "hư hỏng", "đổi trả"]):
            category = "warranty"
        elif any(w in lower for w in ["bảo dưỡng", "thay dầu", "thay lọc", "bảo trì", "kiểm tra xe"]):
            category = "maintenance"
        elif any(w in lower for w in ["pin", "sạc", "dung lượng", "soh", "bms", "chai pin"]):
            category = "battery"
        elif any(w in lower for w in ["đặt lịch", "quy trình", "xưởng", "hẹn"]):
            category = "procedure"
        elif any(w in lower for w in ["an toàn", "cháy nổ", "nguy hiểm", "cứu hộ"]):
            category = "safety"
        else:
            category = "general"

        # 3. Phát hiện mốc km
        milestone = None
        km_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:km|nghìn km|ngàn km)", lower)
        if km_match:
            val_str = km_match.group(1).replace(".", "")
            try:
                val = int(val_str)
                milestone = val * 1000 if val < 1000 else val
            except ValueError:
                pass

        # 4. Viết lại query cơ bản
        rewritten = query
        if found_model and found_model.lower() not in lower:
            rewritten = f"{query} (áp dụng cho xe VinFast {found_model})"

        return QueryAnalysis(
            original_query=query,
            rewritten_query=rewritten,
            keywords=self._fallback_keywords(query),
            model=found_model or "ALL",
            category=category,
            milestone_km=milestone,
            subsystem="battery" if category == "battery" else None,
            is_out_of_scope=False,
        )

    def _fallback_keywords(self, query: str) -> list[str]:
        """Trích xuất từ khóa đơn giản theo token loại bỏ stop-words cơ bản."""
        stop_words = {
            "cho", "tôi", "hỏi", "xe", "của", "và", "là", "có", "không", "thì",
            "những", "gì", "như", "thế", "nào", "ở", "đâu", "với", "được", "bao",
            "nhiêu", "cần", "phải", "làm", "sao", "bị", "đã", "đi", "đang",
        }
        words = re.findall(r"\b[\w\d]+\b", query.lower())
        keywords = [w for w in words if w not in stop_words and len(w) > 1]
        return list(dict.fromkeys(keywords))[:7]

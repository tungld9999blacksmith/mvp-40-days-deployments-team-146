from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    """Schema chuẩn mực cho kết quả thực thi của mọi Tool trong Agent EV Care.

    - status: Trạng thái thực thi ("ok": thành công, "empty": không có kết quả phù hợp, "error": lỗi hạ tầng/nghiệp vụ).
    - code: Mã định danh lỗi hoặc kết quả nghiệp vụ (ví dụ: "DB_UNAVAILABLE", "NO_SLOT", "NOT_OWNER", "DATA_INCOMPLETE", "CONFIRMATION_REQUIRED", "OUTCOME_UNKNOWN").
    - data: Dữ liệu payload thực tế trả về.
    - hint: Thông điệp an toàn, trung thực định hướng LLM cách diễn đạt cho người dùng khi status != "ok".
    """

    status: Literal["ok", "empty", "error"]
    code: str | None = Field(default=None, description="Mã định danh kết quả/lỗi nghiệp vụ")
    data: dict[str, Any] | None = Field(default=None, description="Dữ liệu payload thực tế")
    hint: str | None = Field(default=None, description="Câu gợi ý an toàn định hướng LLM phản hồi")

    def for_llm(self) -> str:
        """Định dạng chuỗi JSON tinh gọn để đưa vào content của ToolMessage cho LLM."""
        payload: dict[str, Any] = {"status": self.status}
        if self.code:
            payload["code"] = self.code
        if self.hint:
            payload["hint"] = self.hint
        if self.data is not None:
            payload["data"] = self.data
        return json.dumps(payload, ensure_ascii=False)

    # ── Tương thích ngược với dict / list indexing của test suite cũ ──
    def __getitem__(self, item: Any) -> Any:
        if isinstance(item, int):
            # Nếu data chứa list xưởng hoặc items
            if self.data and "workshops" in self.data and isinstance(self.data["workshops"], list):
                return self.data["workshops"][item]
            if self.data and "items" in self.data and isinstance(self.data["items"], list):
                return self.data["items"][item]
            raise IndexError(f"ToolResult index out of range: {item}")

        # Ưu tiên tra cứu trong data payload nếu có
        if self.data is not None and isinstance(self.data, dict) and item in self.data:
            return self.data[item]
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(f"Key '{item}' không tồn tại trong ToolResult hoặc data")

    def __contains__(self, item: Any) -> bool:
        if hasattr(self, item):
            return True
        if self.data is not None and isinstance(self.data, dict):
            return item in self.data
        return False

    def __len__(self) -> int:
        if self.data and "workshops" in self.data and isinstance(self.data["workshops"], list):
            return len(self.data["workshops"])
        if self.data and "items" in self.data and isinstance(self.data["items"], list):
            return len(self.data["items"])
        if self.data is not None and isinstance(self.data, dict):
            return len(self.data)
        return 0

    def __iter__(self) -> Iterator[Any]:  # type: ignore[override]
        if self.data and "workshops" in self.data and isinstance(self.data["workshops"], list):
            return iter(self.data["workshops"])
        if self.data and "items" in self.data and isinstance(self.data["items"], list):
            return iter(self.data["items"])
        if self.data is not None and isinstance(self.data, dict):
            return iter(self.data)
        return iter([])

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except (KeyError, IndexError):
            return default

# Entity Specification — Agent trả lời theo phong cách giao tiếp

> Entity cho Feature `FEAT-P2-PS05`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ps-05-phase2-spec.ff.md). **API:** [API Spec](ps-05-phase2-spec.api.md).
>
> **Nguyên tắc (FF §14, §21):** không bảng mới. Phong cách lâu dài là mục nhớ `communication_style` của PS-01 (`agent_user_memory`): chủ xe chọn ⇒ `OWNER_STATED`; hệ thống suy ra ⇒ `INFERRED`. Tín hiệu trong hội thoại được tính từ `chat_message` mỗi lượt, không lưu riêng. **Không lưu nhãn cảm xúc** (bực bội) ở bất kỳ bảng nào.

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-PS05` — PS-05 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | AI Team |
| Created Date | `2026-10-12` |
| Related FF | [ps-05-phase2-spec.ff.md](ps-05-phase2-spec.ff.md) |
| Related API | [ps-05-phase2-spec.api.md](ps-05-phase2-spec.api.md) |
| Related FE | [ps-05-phase2-spec.fe.md](ps-05-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Thay đổi |
|---|---|---|---|
| — | `AgentUserMemory` | `agent_user_memory` (PS-01) | Dùng khoá `communication_style`; schema giá trị §2 |
| `ENT-422` | `ChatMessage` | `chat_message` | Không đổi cột; `refs.style` ghi phong cách đã áp cho tin trợ lý (để eval) |

---

# 2. Giá trị `communication_style`

```json
{ "mode": "AUTO" | "MANUAL",
  "length": "SHORT" | "DETAILED" | null,
  "technical": "PLAIN" | "TECHNICAL" | null,
  "priceFocus": true | false | null,
  "urgency": "HIGH" | null,
  "addressing": null,
  "confidence": 0.8,
  "conversationsObserved": 3 }
```

| Trường | Ghi chú |
|---|---|
| `mode` | `MANUAL` khi chủ xe chọn ở SCR-PS05-01 (`source = OWNER_STATED`), luôn thắng (BR-PS05-03). `AUTO` = để hệ thống suy ra |
| `length`, `technical`, `priceFocus`, `urgency` | Bốn chiều (FF §2.1); `null` = chưa đủ tín hiệu / mặc định |
| `addressing` | Không dùng ở đây — xưng hô là khoá riêng `addressing` của PS-01 |
| `confidence`, `conversationsObserved` | Chỉ cho `INFERRED`; áp khi `conversationsObserved ≥ MEMORY_INFER_MIN_REPEAT` (BR-PS05-05); giảm khi chủ xe hay bấm "Xem chi tiết" (AF-PS05-01) |

Không có chiều nào về tính cách, nhân khẩu học hay cảm xúc (BR-PS05-01).

`refs.style` trên tin trợ lý: `{ "length": "SHORT", "technical": "PLAIN", "source": "INFERRED" | "MANUAL" | "CONVERSATION" | "DEFAULT" }`.

---

# 3. Migration

Không có migration schema. Cập nhật schema giá trị `communication_style` trong `validate_value` (PS-01).

---

# 4. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |

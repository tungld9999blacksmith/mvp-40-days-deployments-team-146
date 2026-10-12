# API Technical Specification — Agent trả lời theo phong cách giao tiếp

> Backend cho Feature `FEAT-P2-PS05`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ps-05-phase2-spec.ff.md). **Entity:** [Entity Spec](ps-05-phase2-spec.entity.md).
>
> **Tái dùng:** `MemoryService` (PS-01: `communication_style`, `propose`, `recall_for_intent`), orchestrator + prompt (`agents/prompts.py`, file prompt riêng), guard đầu ra, thẻ CH-02 (số liệu nằm trên thẻ, không phụ thuộc phong cách), PL-02 `HandoffService` (đề nghị chuyển người), eval harness (`eval/`).

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-PS05` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/agents/style/` (mới): `signals.py` (hàm thuần), `policy.py`, prompt `style_guidance.md`; route trong `modules/agent_memory/route.py` |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `API-PS05-01` | `GET` | `/agent-memory/communication-style` | Phong cách hiện tại (SCR-PS05-01) | UC-PS05-02 |
| `API-PS05-02` | `PUT` | `/agent-memory/communication-style` | Chọn thủ công / về Tự động | UC-PS05-02, BR-PS05-03 |
| `SVC-PS05-01` | Internal | `StyleResolver.resolve(user, conversation)` | Phong cách áp cho lượt | UC-PS05-01 |
| `SVC-PS05-02` | Internal | `FrustrationDetector.check(turn)` | Đề nghị chuyển người | UC-PS05-03, BR-PS05-04 |
| `JOB-PS05-01` | Celery | `style.infer` (sau khi hội thoại nghỉ 30 phút) | Suy ra phong cách | BR-PS05-05 |

---

# 2. `StyleResolver.resolve` (mỗi lượt, ≤ 5 ms)

Thứ tự (BR-PS05-03, EDGE-PS05-01):
1. Lựa chọn thủ công: `communication_style.mode = MANUAL` (đọc được khi có `CONSENT_LONG_TERM_MEMORY`), hoặc header `X-Style-Preference` khi bộ nhớ tắt (xem ghi chú) ⇒ source `MANUAL`.
2. Mục `INFERRED` đủ điều kiện (`conversationsObserved ≥ MEMORY_INFER_MIN_REPEAT`, `confidence ≥ 0,6`) và có đồng ý ⇒ dùng.
3. Tín hiệu trong hội thoại hiện tại (`signals.py` trên ≤ 10 tin chủ xe gần nhất) khi ≥ 3 lượt ⇒ `CONVERSATION`.
4. Mặc định (`DEFAULT`): độ dài vừa, ít thuật ngữ.

> Ghi chú: để lựa chọn thủ công vẫn có hiệu lực khi bộ nhớ dài hạn tắt, `API-PS05-02` lưu thêm vào `localStorage` phía client và frontend gửi header `X-Style-Preference` mỗi lượt; backend dùng header khi không đọc được mục nhớ. Không lưu server khi chưa có đồng ý.

## 2.1 Tín hiệu (`signals.py`, hàm thuần)

| Chiều | Tín hiệu |
|---|---|
| `length` | Trung vị độ dài tin chủ xe ≤ 25 ký tự ⇒ `SHORT`; ≥ 120 ký tự hoặc hỏi "tại sao / giải thích" ⇒ `DETAILED` |
| `technical` | Tỉ lệ thuật ngữ (danh sách: "SoC", "BMS", "kWh", "inverter", "má phanh", "dầu phanh DOT"…) ⇒ `TECHNICAL`; hỏi lại nghĩa từ ⇒ `PLAIN` |
| `priceFocus` | ≥ 2 câu hỏi giá / tổng số câu ≥ 30 % |
| `urgency` | Từ "gấp", "ngay", "hôm nay", "sắp hỏng" ⇒ `HIGH` (chỉ trong hội thoại, không lưu dài hạn) |

---

# 3. Áp phong cách vào câu trả lời (BR-PS05-02)

- Prompt hệ thống thêm khối `STYLE` ngắn (độ dài, mức thuật ngữ, thứ tự: giá trước khi `priceFocus`, việc cần làm trước khi `urgency`).
- **Bất biến:** số liệu, nguồn, cảnh báo an toàn, giá, bảo hành **không** do phong cách quyết định — chúng nằm trên thẻ CH-02 hoặc trong khối "bắt buộc giữ" mà guard đầu ra kiểm: mọi số tiền / km / ngày và mọi citation trong kết quả tool phải xuất hiện như nhau ở câu trả lời hoặc thẻ.
- `SHORT`: chữ ≤ 3 câu, chip "Xem chi tiết" (CH-01, intent `expand_last_answer` — trả bản `DETAILED` của cùng nội dung, không gọi lại tool).
- Nội dung an toàn (AD-02 `SAFETY_ADVICE`, cảnh báo dừng xe) bỏ qua phong cách, luôn đầy đủ (EF-PS05-01, AC-PS05-02).
- Ghi `chat_message.refs.style`.
- Độ trễ thêm ≤ 10 % (FF §18): không gọi LLM phụ; chỉ thêm ~80 token prompt.

---

# 4. API-PS05-01/02

- `GET` ⇒ `{ mode, length, technical, source, inferred: { length, technical, confidence } | null }`.
- `PUT { "mode": "MANUAL", "preset": "SHORT" | "DETAILED" | "PLAIN" }` ⇒ ánh xạ preset ⇒ chiều; có đồng ý bộ nhớ ⇒ `MemoryService.propose(communication_style, source = OWNER_STATED)`; không ⇒ trả `{ "stored": "CLIENT_ONLY" }` (frontend giữ cục bộ, §2 ghi chú). `{ "mode": "AUTO" }` ⇒ xoá lựa chọn thủ công.

---

# 5. `FrustrationDetector` (BR-PS05-04)

- Tín hiệu trong lượt: lặp lại gần nguyên câu ≥ 2 lần, từ ngữ tiêu cực (danh sách cấu hình), viết hoa toàn bộ, "nói chuyện với người", "không hiểu à".
- `frustration = HIGH` ⇒ trợ lý thêm câu đề nghị + chip "Gặp người của xưởng" (PL-02, `reason = FRUSTRATION`, chỉ tạo khi chủ xe bấm). Không lưu nhãn (FF §21); chỉ PL-03 đếm `handoff_created` khi có.
- Tối đa một lần đề nghị mỗi hội thoại / 30 phút.

---

# 6. JOB-PS05-01 — suy ra

Khi hội thoại nghỉ 30 phút và có ≥ 3 lượt: tính tín hiệu (§2.1, trừ `urgency`) ⇒ `propose(communication_style, source = INFERRED)` (PS-01 cộng `conversationsObserved` khi nhất quán, giảm `confidence` khi mâu thuẫn hoặc khi chủ xe bấm "Xem chi tiết" ≥ 2 lần trong hội thoại `SHORT` — AF-PS05-01). Chỉ khi có đồng ý bộ nhớ (EDGE-PS05-01).

---

# 7. Eval & Test Checklist

| Layer | What | Count |
|---|---|---|
| Unit | `signals.py` cho 4 chiều | +6 |
| Unit | Thứ tự resolve: thủ công > suy ra > hội thoại > mặc định | +4 |
| Eval | Cùng câu hỏi × 4 phong cách ⇒ cùng con số, cùng nguồn (AC-PS05-01) | 1 bộ (`eval/datasets/style_invariance`) |
| Eval | Cảnh báo an toàn đầy đủ ở mọi phong cách (AC-PS05-02) | 1 bộ |
| Service | Bực bội ⇒ chip đề nghị, không tự tạo handoff; không lưu nhãn | +2 |
| Perf | Độ trễ token đầu tăng ≤ 10 % | +1 |

---

# 8. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
